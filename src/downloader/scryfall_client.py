"""Async Scryfall API client for downloading card images with progress tracking."""

import asyncio
import os
import shutil
from typing import Callable

import httpx

from src.models import CardEntry
from src.scryfall_http import create_scryfall_client
from src.transformer_files import (
    build_transformer_face_filename,
    build_transformer_group_id,
    sanitize_filename,
)


_CHUNK_SIZE = 75
_RATE_LIMIT_SECONDS = 0.1

ProgressCallback = Callable[[int, int, str], None]
LogCallback = Callable[[str, str], None]


def _noop_progress(current: int, total: int, name: str) -> None:
    pass


def _noop_log(level: str, message: str) -> None:
    pass


async def download_card_images(
    card_entries: list[CardEntry],
    order_name: str,
    include_tokens: bool = False,
    dual_face_token: bool = False,
    on_progress: ProgressCallback = _noop_progress,
    on_log: LogCallback = _noop_log,
) -> dict:
    """Download card images from Scryfall for all entries in the list."""
    os.makedirs(order_name, exist_ok=True)

    identifiers: list[dict] = []
    quantity_map: dict[str, int] = {}
    entry_map: dict[str, CardEntry] = {}
    failed_items: list[dict] = []
    error_log_path: str | None = None
    token_ids: set[str] = set()

    for entry in card_entries:
        identifier = {"set": entry.set_code, "collector_number": entry.collector_number}
        identifiers.append(identifier)
        key = f"{entry.set_code}|{entry.collector_number}"
        quantity_map[key] = entry.quantity
        entry_map[key] = entry

    if not identifiers:
        on_log("WARN", "No valid card entries to download.")
        return {"downloaded": 0, "failed": failed_items, "error_log_path": None}

    total_cards = len(identifiers)
    downloaded_count = 0

    async with create_scryfall_client(timeout=30.0) as client:
        for chunk_idx in range(0, len(identifiers), _CHUNK_SIZE):
            chunk = identifiers[chunk_idx : chunk_idx + _CHUNK_SIZE]
            chunk_num = (chunk_idx // _CHUNK_SIZE) + 1
            total_chunks = (len(identifiers) + _CHUNK_SIZE - 1) // _CHUNK_SIZE

            on_log("INFO", f"Processing chunk {chunk_num} of {total_chunks}...")

            try:
                await asyncio.sleep(_RATE_LIMIT_SECONDS)
                response = await client.post(
                    "https://api.scryfall.com/cards/collection",
                    json={"identifiers": chunk},
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()

                if "data" in data:
                    for card in data["data"]:
                        key = f"{card['set']}|{card['collector_number']}"
                        quantity = quantity_map.get(key, 1)
                        card_name = card.get("name", "Unknown")

                        try:
                            if include_tokens and "all_parts" in card:
                                for part in card["all_parts"]:
                                    if part.get("component") == "token" and "id" in part:
                                        token_ids.add(part["id"])

                            await _process_card(client, card, quantity, order_name, on_log)
                            downloaded_count += 1
                            on_progress(downloaded_count, total_cards, card_name)
                        except Exception as e:
                            on_log("ERROR", f"Failed to download '{card_name}': {e}")
                            failed_items.append({"card": card_name, "reason": str(e)})

                if "not_found" in data:
                    for nf in data["not_found"]:
                        nf_key = f"{nf.get('set', '')}|{nf.get('collector_number', '')}"
                        entry = entry_map.get(nf_key)
                        label = entry.raw_line if entry else str(nf)
                        on_log("WARN", f"Card not found by API: {label}")
                        failed_items.append({"card": label, "reason": "Not found by Scryfall API"})

            except httpx.HTTPStatusError as e:
                on_log("ERROR", f"API error for chunk {chunk_num}: {e}")
                for ident in chunk:
                    ik = f"{ident['set']}|{ident['collector_number']}"
                    entry = entry_map.get(ik)
                    failed_items.append({"card": entry.raw_line if entry else str(ident), "reason": str(e)})
            except httpx.RequestError as e:
                on_log("ERROR", f"Network error for chunk {chunk_num}: {e}")
                for ident in chunk:
                    ik = f"{ident['set']}|{ident['collector_number']}"
                    entry = entry_map.get(ik)
                    failed_items.append({"card": entry.raw_line if entry else str(ident), "reason": str(e)})

        if include_tokens and token_ids:
            on_log("INFO", f"Fetching {len(token_ids)} tokens...")
            token_list = [{"id": tid} for tid in token_ids]
            token_downloaded_count = 0
            token_pair_idx = 1

            for chunk_idx in range(0, len(token_list), _CHUNK_SIZE):
                chunk = token_list[chunk_idx : chunk_idx + _CHUNK_SIZE]
                try:
                    await asyncio.sleep(_RATE_LIMIT_SECONDS)
                    response = await client.post(
                        "https://api.scryfall.com/cards/collection",
                        json={"identifiers": chunk},
                        headers={"Content-Type": "application/json"},
                    )
                    response.raise_for_status()
                    data = response.json()

                    if "data" in data:
                        for token_card in data["data"]:
                            try:
                                if not dual_face_token:
                                    await _process_card(client, token_card, 1, order_name, on_log)
                                else:
                                    await _process_token_dual_face(
                                        client, token_card, token_pair_idx, order_name, on_log
                                    )
                                    token_pair_idx += 1

                                token_downloaded_count += 1
                                on_progress(
                                    downloaded_count + token_downloaded_count,
                                    total_cards + len(token_ids),
                                    token_card.get("name", "Token"),
                                )
                            except Exception as e:
                                on_log("ERROR", f"Failed to download token '{token_card.get('name')}': {e}")
                                failed_items.append({"card": token_card.get("name", "Token"), "reason": str(e)})
                except Exception as e:
                    on_log("ERROR", f"API error fetching tokens: {e}")

            if dual_face_token and len(token_ids) % 2 != 0:
                group_num = (len(token_ids) + 1) // 2
                blank_filename = build_transformer_face_filename("Blank", f"token_{group_num}", 2)
                blank_filepath = os.path.join(order_name, "transformers", blank_filename)
                await asyncio.to_thread(_generate_blank_png, blank_filepath)
                on_log("INFO", f"Generated blank face: {blank_filename}")

    if failed_items:
        error_log_path = _write_error_log(order_name, failed_items)
        on_log("WARN", f"Download finished with failures. Report saved to: {error_log_path}")
    else:
        on_log("INFO", "No failed items. No error report was generated.")

    on_log("INFO", f"Download complete. {downloaded_count} succeeded, {len(failed_items)} failed.")
    return {"downloaded": downloaded_count, "failed": failed_items, "error_log_path": error_log_path}


async def download_single_card_image(
    card: dict,
    quantity: int,
    output_dir: str,
    on_log: LogCallback = _noop_log,
) -> bool:
    """Download a single card's large images to a specific directory."""
    try:
        os.makedirs(output_dir, exist_ok=True)
        async with create_scryfall_client(timeout=30.0) as client:
            await _process_card(client, card, quantity, output_dir, on_log)
        return True
    except Exception as e:
        on_log("ERROR", f"Individual download failed: {e}")
        return False


async def _process_card(
    client: httpx.AsyncClient,
    card: dict,
    quantity: int,
    order_name: str,
    on_log: LogCallback,
) -> None:
    """Process a single card from the API response and create any requested copies."""
    images_to_download: list[dict] = []
    output_dir = order_name
    set_code = card["set"]
    col_num = card["collector_number"]
    top_level_image_url = (card.get("image_uris") or {}).get("large")
    face_images = [
        {
            "url": face["image_uris"]["large"],
            "name": face["name"],
            "face_index": face_index,
        }
        for face_index, face in enumerate(card.get("card_faces", []), start=1)
        if (face.get("image_uris") or {}).get("large")
    ]
    is_transformer = not top_level_image_url and bool(face_images)

    if top_level_image_url:
        images_to_download.append({"url": top_level_image_url, "name": card["name"]})
    elif face_images:
        output_dir = os.path.join(order_name, "transformers")
        os.makedirs(output_dir, exist_ok=True)
        images_to_download.extend(face_images)
    else:
        raise ValueError(f"No image URI found for card: {card.get('name', 'Unknown')}")

    if is_transformer:
        first_copy_group_id = build_transformer_group_id(set_code, col_num, 1)
        first_copy_files: dict[int, tuple[str, str]] = {}

        for img_info in images_to_download:
            safe_name = sanitize_filename(img_info["name"])
            face_index = img_info["face_index"]
            first_filename = build_transformer_face_filename(safe_name, first_copy_group_id, face_index)
            first_filepath = os.path.join(output_dir, first_filename)

            await asyncio.sleep(_RATE_LIMIT_SECONDS)
            img_response = await client.get(img_info["url"])
            img_response.raise_for_status()

            await asyncio.to_thread(_write_file, first_filepath, img_response.content)
            on_log("INFO", f"Saved: {first_filename}")
            first_copy_files[face_index] = (safe_name, first_filepath)

        for copy_index in range(2, quantity + 1):
            group_id = build_transformer_group_id(set_code, col_num, copy_index)
            for face_index, (safe_name, source_path) in first_copy_files.items():
                copy_filename = build_transformer_face_filename(safe_name, group_id, face_index)
                copy_filepath = os.path.join(output_dir, copy_filename)
                await asyncio.to_thread(shutil.copy, source_path, copy_filepath)
                on_log("INFO", f"Saved (copy): {copy_filename}")
        return

    for img_info in images_to_download:
        safe_name = sanitize_filename(img_info["name"])
        first_filename = f"{safe_name}--{set_code}_{col_num}--1.png"
        first_filepath = os.path.join(output_dir, first_filename)

        await asyncio.sleep(_RATE_LIMIT_SECONDS)
        img_response = await client.get(img_info["url"])
        img_response.raise_for_status()

        await asyncio.to_thread(_write_file, first_filepath, img_response.content)
        on_log("INFO", f"Saved: {first_filename}")

        for i in range(2, quantity + 1):
            copy_filename = f"{safe_name}_{set_code}_{col_num}_{i}.png"
            copy_filepath = os.path.join(output_dir, copy_filename)
            await asyncio.to_thread(shutil.copy, first_filepath, copy_filepath)
            on_log("INFO", f"Saved (copy): {copy_filename}")


def _write_file(filepath: str, content: bytes) -> None:
    """Write bytes to a file."""
    with open(filepath, "wb") as f:
        f.write(content)


def _write_error_log(order_name: str, failed_items: list[dict]) -> str:
    """Write a consolidated error log file."""
    error_log_path = os.path.join(order_name, "__error_log.txt")
    with open(error_log_path, "w", encoding="utf-8") as f:
        f.write("The following items could not be processed:\n" + "=" * 40 + "\n")
        for item in failed_items:
            f.write(f"- Card: {item['card']}\n")
            f.write(f"  Reason: {item['reason']}\n\n")
    return error_log_path


async def _process_token_dual_face(
    client: httpx.AsyncClient,
    card: dict,
    idx: int,
    order_name: str,
    on_log: LogCallback,
) -> None:
    """Process a single token for two-sided transformer layout."""
    output_dir = os.path.join(order_name, "transformers")
    os.makedirs(output_dir, exist_ok=True)

    group_num = (idx + 1) // 2
    face_num = 1 if idx % 2 != 0 else 2

    images_to_download: list[dict] = []
    top_level_image_url = (card.get("image_uris") or {}).get("large")
    if top_level_image_url:
        images_to_download.append({"url": top_level_image_url, "name": card["name"]})
    else:
        for face in card.get("card_faces", []):
            face_image_url = (face.get("image_uris") or {}).get("large")
            if face_image_url:
                images_to_download.append({"url": face_image_url, "name": face["name"]})
                break

    if not images_to_download:
        raise ValueError(f"No image URI found for token: {card.get('name', 'Unknown')}")

    for img_info in images_to_download:
        filename = build_transformer_face_filename(img_info["name"], f"token_{group_num}", face_num)
        filepath = os.path.join(output_dir, filename)

        await asyncio.sleep(_RATE_LIMIT_SECONDS)
        img_response = await client.get(img_info["url"])
        img_response.raise_for_status()

        await asyncio.to_thread(_write_file, filepath, img_response.content)
        on_log("INFO", f"Saved token: {filename}")


def _generate_blank_png(filepath: str) -> None:
    """Generate a 1x1 transparent PNG for completing odd token pairs."""
    import base64

    transparent_png_b64 = (
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    content = base64.b64decode(transparent_png_b64)
    with open(filepath, "wb") as f:
        f.write(content)
