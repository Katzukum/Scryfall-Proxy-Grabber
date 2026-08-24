"""pywebview JS API class — bridges all backend modules to the frontend."""

import asyncio
import os
import re
import threading
from tkinter import filedialog
from typing import Any

import webview

from src.models import PrintSettings, OutputFormat
from src.downloader.list_cleaner import parse_deck_list
from src.downloader.scryfall_client import download_card_images, download_single_card_image
from src.print_setup.pdf_renderer import create_proxy_pdf, create_transformer_pdf
from src.print_setup.png_renderer import create_proxy_png, create_transformer_png
from src.card_lookup.scryfall_search import (
    autocomplete_card_name,
    search_card_by_name,
    lookup_card_by_set,
)


class Api:
    """pywebview JS API exposed to the frontend via window.pywebview.api."""

    def __init__(self) -> None:
        self._window: webview.Window | None = None

    def set_window(self, window: webview.Window) -> None:
        """Set the webview window reference for JS callbacks."""
        self._window = window

    # --- Utility ---

    def _push_log(self, level: str, message: str) -> None:
        """Push a log message to the frontend."""
        if self._window:
            safe_msg = message.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
            self._window.evaluate_js(f"window.__pushLog && window.__pushLog('{level}', '{safe_msg}')")

    def _push_progress(self, current: int, total: int, label: str) -> None:
        """Push a progress update to the frontend."""
        if self._window:
            safe_label = label.replace("\\", "\\\\").replace("'", "\\'")
            self._window.evaluate_js(
                f"window.__pushProgress && window.__pushProgress({current}, {total}, '{safe_label}')"
            )

    def _push_task_complete(self, result: Any = None) -> None:
        """Signal task completion to the frontend."""
        if self._window:
            import json
            result_json = json.dumps(result) if result is not None else "null"
            self._window.evaluate_js(f"window.__onTaskComplete && window.__onTaskComplete({result_json})")

    # --- Downloader Tab ---

    def start_download(self, order_name: str, card_list_text: str, include_tokens: bool = False, dual_face_token: bool = False) -> None:
        """Start downloading card images in a background thread.

        Args:
            order_name: Folder name for the download.
            card_list_text: Raw deck list text from the UI.
            include_tokens: Whether to fetch related token cards.
            dual_face_token: Whether to pair tokens for 2-sided transformer layouts.
        """
        def _run() -> None:
            try:
                self._push_log("INFO", f"Starting download: {order_name}")
                self._push_log("INFO", "Parsing card list...")

                entries = parse_deck_list(card_list_text)
                if not entries:
                    self._push_log("ERROR", "No valid card entries found in the list.")
                    self._push_task_complete({"success": False, "error": "No valid entries"})
                    return

                self._push_log("INFO", f"Parsed {len(entries)} card entries.")

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(
                    download_card_images(
                        card_entries=entries,
                        order_name=order_name,
                        include_tokens=include_tokens,
                        dual_face_token=dual_face_token,
                        on_progress=self._push_progress,
                        on_log=self._push_log,
                    )
                )
                loop.close()

                self._push_task_complete({"success": True, **result})
            except Exception as e:
                self._push_log("ERROR", f"Critical error: {e}")
                self._push_task_complete({"success": False, "error": str(e)})

        threading.Thread(target=_run, daemon=True).start()

    def get_error_cards(self, order_name: str) -> list[str]:
        """Return unique card names listed in the order's error log.

        Args:
            order_name: Order folder name where the error log is stored.

        Returns:
            List of card names that failed to download. Empty if no log exists.
        """
        log_candidates = [
            os.path.join(order_name, "__error_log.txt"),
            os.path.join(order_name, "error_log.txt"),
        ]
        error_log_path = next((p for p in log_candidates if os.path.isfile(p)), None)
        if not error_log_path:
            return []

        names: list[str] = []
        seen: set[str] = set()
        card_line_pattern = re.compile(r"^\s*-\s*Card:\s*(.+?)\s*$")
        deck_line_pattern = re.compile(r"^\s*\d+\s+(.+?)\s+\((\w{2,5})\)\s+[\w\d-]+")

        with open(error_log_path, "r", encoding="utf-8") as f:
            for line in f:
                match = card_line_pattern.match(line)
                if not match:
                    continue

                raw_label = match.group(1).strip()
                deck_match = deck_line_pattern.match(raw_label)
                card_name = deck_match.group(1).strip() if deck_match else raw_label
                if not card_name:
                    continue

                key = card_name.casefold()
                if key in seen:
                    continue
                seen.add(key)
                names.append(card_name)

        return names

    # --- Print Setup Tab ---

    def get_default_settings(self) -> dict:
        """Return default print settings as a dict."""
        return PrintSettings().model_dump()

    def browse_folder(self) -> str:
        """Open a native folder picker dialog.

        Returns:
            Selected folder path, or empty string if cancelled.
        """
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if result and len(result) > 0:
            return result[0]
        return ""

    def create_output(
        self,
        image_folder: str,
        card_width: float,
        card_height: float,
        corner_radius: float,
        padding: float,
        output_format: str,
        is_transformer: bool,
    ) -> None:
        """Create PDF or PNG output in a background thread.

        Args:
            image_folder: Path to the folder containing card images.
            card_width: Card width in mm.
            card_height: Card height in mm.
            corner_radius: Corner radius in mm.
            padding: Padding between cards in mm.
            output_format: 'pdf' or 'png'.
            is_transformer: Whether to use two-sided layout.
        """
        def _run() -> None:
            try:
                settings = PrintSettings(
                    card_width_mm=card_width,
                    card_height_mm=card_height,
                    corner_radius_mm=corner_radius,
                    padding_mm=padding,
                    output_format=OutputFormat(output_format),
                    is_transformer=is_transformer,
                )

                target_folder = image_folder
                if is_transformer:
                    target_folder = os.path.join(image_folder, "transformers")

                if settings.output_format == OutputFormat.PDF:
                    if is_transformer:
                        result = create_transformer_pdf(
                            target_folder, settings, on_log=self._push_log, on_progress=self._push_progress
                        )
                    else:
                        result = create_proxy_pdf(
                            target_folder, settings, on_log=self._push_log, on_progress=self._push_progress
                        )
                    self._push_task_complete({"success": True, "output": result})
                else:
                    if is_transformer:
                        result = create_transformer_png(
                            target_folder, settings, on_log=self._push_log, on_progress=self._push_progress
                        )
                    else:
                        result = create_proxy_png(
                            target_folder, settings, on_log=self._push_log, on_progress=self._push_progress
                        )
                    self._push_task_complete({"success": True, "output": result})

            except Exception as e:
                self._push_log("ERROR", f"Critical error: {e}")
                self._push_task_complete({"success": False, "error": str(e)})

        threading.Thread(target=_run, daemon=True).start()

    # --- Card Lookup Tab ---

    def autocomplete_card(self, query: str) -> list[str]:
        """Get autocomplete suggestions for a card name.

        Args:
            query: Partial card name (min 2 characters).

        Returns:
            List of matching card name strings.
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(autocomplete_card_name(query))
            loop.close()
            return result
        except Exception:
            return []

    def search_card(self, name: str) -> list[dict]:
        """Search for a card by name (finds all printings).

        Args:
            name: Card name to search.

        Returns:
            List of card data dicts.
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(search_card_by_name(name))
            loop.close()
            return [r.model_dump() for r in results]
        except Exception as e:
            self._push_log("ERROR", f"Search error: {e}")
            return []

    def lookup_card(self, set_code: str, collector_number: str) -> list[dict]:
        """Look up a specific card by set code and collector number.

        Args:
            set_code: Set code (e.g., 'mh2').
            collector_number: Collector number.

        Returns:
            List of card data dicts (usually one).
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(lookup_card_by_set(set_code, collector_number))
            loop.close()
            return [r.model_dump() for r in results]
        except Exception as e:
            self._push_log("ERROR", f"Lookup error: {e}")
            return []
    def download_single_card(self, card_data: dict, quantity: int, folder: str) -> None:
        """Download a single card multiple times in a background thread.

        Args:
            card_data: Raw Scryfall card JSON.
            quantity: Number of copies.
            folder: Destination folder path.
        """
        def _run() -> None:
            try:
                self._push_log("INFO", f"Downloading {quantity} copies of '{card_data.get('name')}' to {folder}")
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                success = loop.run_until_complete(
                    download_single_card_image(
                        card=card_data,
                        quantity=quantity,
                        output_dir=folder,
                        on_log=self._push_log,
                    )
                )
                loop.close()

                if success:
                    self._push_log("INFO", f"Finished downloading '{card_data.get('name')}'")
                self._push_task_complete({"success": success})
            except Exception as e:
                self._push_log("ERROR", f"Individual download error: {e}")
                self._push_task_complete({"success": False, "error": str(e)})

        threading.Thread(target=_run, daemon=True).start()
