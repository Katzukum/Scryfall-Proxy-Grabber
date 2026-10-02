"""Card preparation and isolated, cancellable DeckTheme background jobs."""

from __future__ import annotations

import asyncio
import base64
import copy
import io
import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import urlparse

from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from src.scryfall_http import create_scryfall_client


MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_PIXELS = 32_000_000


def data_directory() -> Path:
    """Keep large downloads outside the executable and PyInstaller extraction folder."""
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / ".local" / "share") / "ProxyToolBox" / "deck-theme"


class EditOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card_id: str
    theme: str = Field(min_length=1, max_length=4000)
    prompt: str = Field(min_length=1, max_length=16000)
    width: StrictInt = Field(ge=256, le=2048)
    height: StrictInt = Field(ge=256, le=2048)
    steps: StrictInt = Field(ge=1, le=50)
    seed: StrictInt = Field(ge=0, le=2_147_483_647)
    device: Literal["auto", "cpu"] = "auto"


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _image_data(path: Path) -> str:
    with Image.open(path) as source:
        preview = source.convert("RGB")
        preview.thumbnail((768, 1088))
        buffer = io.BytesIO()
        preview.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _normalize_image(content: bytes, path: Path) -> None:
    if len(content) > MAX_IMAGE_BYTES:
        raise ValueError("Choose an image smaller than 32 MB.")
    with Image.open(io.BytesIO(content)) as source:
        if source.width * source.height > MAX_IMAGE_PIXELS or min(source.size) < 64:
            raise ValueError("Choose an image at least 64 pixels wide and high, and below 32 megapixels.")
        image = ImageOps.exif_transpose(source).convert("RGB")
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, format="PNG")


def _card_fields(card: dict, face_index: int) -> tuple[dict, str]:
    """Use the exact chosen face; combined-layout cards retain their full metadata."""
    if not isinstance(card, dict):
        raise ValueError("Select a card first.")
    faces = card.get("card_faces") or []
    if type(face_index) is not int or face_index < 0 or face_index >= max(1, len(faces)):
        raise ValueError("That card face is unavailable.")
    chosen = faces[face_index] if faces and faces[face_index].get("image_uris") else card
    uris = chosen.get("image_uris") or {}
    url = uris.get("png") or uris.get("large") or uris.get("normal")
    if not isinstance(url, str):
        raise ValueError("This printing has no card image. Choose another printing.")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"cards.scryfall.io", "c1.scryfall.com"}:
        raise ValueError("The card image must come from Scryfall's image service.")
    fields = {
        "name": str(card.get("name") or "Card"),
        "face_name": str(chosen.get("name") or card.get("name") or "Card"),
        "set_code": str(card.get("set") or "").upper(),
        "collector_number": str(card.get("collector_number") or ""),
    }
    for key in ("oracle_text", "mana_cost", "type_line", "flavor_text"):
        value = chosen.get(key)
        if not value and chosen is card and faces:
            value = " // ".join(str(face[key]) for face in faces if face.get(key))
        fields[key] = str(value or "")
    return fields, url


async def _fetch_card_image(url: str) -> bytes:
    async with create_scryfall_client(timeout=60.0) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > MAX_IMAGE_BYTES:
                    raise ValueError("The source image exceeds the 32 MB limit.")
            return bytes(content)


class DeckThemeService:
    def __init__(self, root: Path | None = None, assets=None, on_log: Callable[[str, str], None] | None = None):
        self.root = root or data_directory()
        if assets is None:
            from .assets import AssetManager

            assets = AssetManager(self.root)
        self.assets = assets
        self.on_log = on_log or (lambda level, message: None)
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._job: dict | None = None
        last_job = self.root / "last-job.json"
        if last_job.exists():
            try:
                saved = json.loads(last_job.read_text(encoding="utf-8"))
                if isinstance(saved, dict) and saved.get("state") in {"running", "complete", "cancelled", "failed"}:
                    self._job = saved
                    if saved["state"] == "running":
                        saved.update(state="failed", error="The app closed before this task finished. You can retry it.",
                                     message="Interrupted by app shutdown")
            except (OSError, ValueError):
                pass

    def status(self) -> dict:
        return {**self.assets.status(), "job": self.job()}

    def job(self) -> dict | None:
        with self._lock:
            return copy.deepcopy(self._job)

    def _persist_job(self) -> None:
        if self._job:
            _write_json(self.root / "last-job.json", self._job)
            _write_json(self.root / "jobs" / f"{self._job['id']}.json", self._job)

    def _store_card(self, content: bytes, fields: dict) -> dict:
        card_id = uuid.uuid4().hex
        directory = self.root / "cards" / card_id
        _normalize_image(content, directory / "source.png")
        card = {"id": card_id, **fields}
        _write_json(directory / "card.json", card)
        return {**card, "image": _image_data(directory / "source.png")}

    def prepare_card(self, raw_card: dict, face_index: int = 0) -> dict:
        fields, url = _card_fields(raw_card, face_index)
        return self._store_card(asyncio.run(_fetch_card_image(url)), fields)

    def import_image(self, path: str) -> dict:
        source = Path(path)
        if source.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError("Choose an image smaller than 32 MB.")
        fields = {"name": source.stem, "face_name": source.stem, "set_code": "", "collector_number": "",
                  "oracle_text": "", "mana_cost": "", "type_line": "", "flavor_text": ""}
        return self._store_card(source.read_bytes(), fields)

    def _card(self, card_id: str) -> tuple[dict, Path]:
        if not isinstance(card_id, str) or not re.fullmatch(r"[a-f0-9]{32}", card_id):
            raise ValueError("Select a card or import an image first.")
        directory = self.root / "cards" / card_id
        try:
            card = json.loads((directory / "card.json").read_text(encoding="utf-8"))
            if not (directory / "source.png").is_file():
                raise FileNotFoundError
            return card, directory / "source.png"
        except (OSError, ValueError) as exc:
            raise ValueError("The source card is unavailable. Please load it again.") from exc

    def build_prompt(self, card_id: str, theme: str) -> str:
        card, _ = self._card(card_id)
        theme = self._validate_text(theme, "theme", 4000)
        facts = "\n".join(f"{label}: {card[key]}" for key, label in (
            ("face_name", "Card"), ("mana_cost", "Mana cost"), ("type_line", "Type"),
            ("oracle_text", "Rules / effect"), ("flavor_text", "Flavor text"))
            if card.get(key))
        return (
            f"Edit <image1>, the supplied card image, using this theme: {theme}\n\n"
            "Inspect the original illustration and composition. Reimagine its subjects, setting, colors, and "
            "decorative frame to fit the theme while retaining a clear connection to this card's identity and effect. "
            "Use the card facts below as creative context. Preserve the visible card name, mana symbols, rules text, "
            "numbers, and their legibility. Keep the full card, its orientation, and aspect ratio. "
            "Return one finished card image without additional captions or mockup surroundings.\n\n"
            f"Card facts:\n{facts}"
        )

    @staticmethod
    def _validate_text(value: str, label: str, limit: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError(f"Enter a {label} between 1 and {limit:,} characters.")
        return value.strip()

    def _begin(self, kind: str, message: str, work: Callable) -> dict:
        with self._lock:
            if self._job and self._job["state"] == "running":
                raise ValueError("A DeckTheme task is already running. Wait for it or cancel it first.")
            self._cancel = threading.Event()
            cancel = self._cancel
            self._job = {"id": uuid.uuid4().hex, "kind": kind, "state": "running", "current": 0,
                         "total": 0, "message": message}
            initial = copy.deepcopy(self._job)
            job_id = self._job["id"]
            started = time.monotonic()
            log_path = self.root / "jobs" / f"{job_id}.log"
            logged_bytes = 0

            def progress(current: int, total: int, detail: str) -> None:
                if cancel.is_set():
                    raise InterruptedError("Cancelled")
                with self._lock:
                    self._job.update(current=current, total=total, message=str(detail)[-600:])

            def log(detail: str) -> None:
                nonlocal logged_bytes
                progress(0, 0, detail)
                # Keep stage timings for performance diagnosis without growing an
                # unbounded log or putting native output in the global UI console.
                line = f"{time.monotonic() - started:.2f}s {str(detail)[-2000:]}\n"
                if logged_bytes + len(line.encode("utf-8")) <= 2 * 1024 * 1024:
                    try:
                        with log_path.open("a", encoding="utf-8") as stream:
                            stream.write(line)
                        logged_bytes += len(line.encode("utf-8"))
                    except OSError:
                        pass  # Diagnostics must not abort an otherwise usable job.

            def run() -> None:
                try:
                    result = work(job_id, cancel, progress, log) or {}
                    if cancel.is_set():
                        raise InterruptedError("Cancelled")
                    result["elapsed_seconds"] = round(time.monotonic() - started, 1)
                    if log_path.is_file():
                        result["runtime_log"] = str(log_path)
                    final = {"state": "complete", "message": "Finished", "result": result}
                except InterruptedError:
                    final = {"state": "cancelled", "message": "Cancelled. Completed downloads are kept."}
                except Exception as exc:
                    final = {"state": "cancelled" if cancel.is_set() else "failed",
                             "message": "Cancelled" if cancel.is_set() else "Task failed", "error": str(exc)}
                    self._log("ERROR", f"DeckTheme: {exc}")
                finally:
                    with self._lock:
                        self._job.update(final)
                        try:
                            self._persist_job()
                        except OSError as exc:
                            self._log("ERROR", f"Could not save DeckTheme task status: {exc}")
                if final["state"] == "complete":
                    self._log("INFO", f"DeckTheme {kind} completed in {result['elapsed_seconds']} s.")

            try:
                self._persist_job()
                self._thread = threading.Thread(target=run, name=f"DeckTheme-{kind}", daemon=True)
                self._thread.start()
            except Exception as exc:
                # A failed startup has no worker to clear the running state.
                self._thread = None
                self._job.update(state="failed", message="Could not start task", error=str(exc))
                try:
                    self._persist_job()
                except OSError:
                    pass
                raise
            return initial

    def _log(self, level: str, message: str) -> None:
        try:
            self.on_log(level, message)
        except Exception:
            pass  # A closing window must not prevent worker cleanup.

    def start_download(self, group: str) -> dict:
        if group not in {"editor", "enhancer"}:
            raise ValueError("Unknown model download.")

        def work(job_id, cancel, progress, log):
            from .editor_session import close_editor_session

            close_editor_session()
            self.assets.install(group, cancel, progress)

        return self._begin("download", "Preparing model download…", work)

    def start_enhance(self, card_id: str, theme: str, prompt: str, device: str = "auto") -> dict:
        _, source = self._card(card_id)
        self._validate_text(theme, "theme", 4000)
        prompt = self._validate_text(prompt, "prompt", 16000)
        if device not in {"auto", "cpu"}:
            raise ValueError("Choose Automatic GPU or CPU.")
        if not self.assets.status()["enhancer"]["ready"]:
            raise ValueError("Download the prompt enhancement model first.")

        def work(job_id, cancel, progress, log):
            from .engine import enhance_prompt
            from .editor_session import close_editor_session

            close_editor_session()
            rewritten = enhance_prompt(self.assets, source, prompt, device, cancel, log)
            return {"prompt": rewritten, "card_id": card_id}

        return self._begin("enhance", "Loading prompt enhancer…", work)

    def start_edit(self, options: dict) -> dict:
        request = EditOptions.model_validate(options)
        card, source = self._card(request.card_id)
        self._validate_text(request.prompt, "prompt", 16000)
        self._validate_text(request.theme, "theme", 4000)
        if request.width % 32 or request.height % 32 or request.width * request.height > 2_097_152:
            raise ValueError("Image dimensions must be multiples of 32 and no larger than 2 megapixels.")
        if not self.assets.status()["editor"]["ready"]:
            raise ValueError("Download the image editing model first.")

        def work(job_id, cancel, progress, log):
            from .engine import edit_image

            prepare_runtime = getattr(self.assets, "prepare_editor_runtime", None)
            if prepare_runtime is not None:
                selected = prepare_runtime(request.device, cancel, progress)
                log(f"Image runtime: {selected.upper()}" if request.device != "cpu" else "Image runtime: CPU")
            folder = self.root / "outputs" / job_id
            folder.mkdir(parents=True, exist_ok=True)
            slug = re.sub(r"[^\w-]+", "-", card["face_name"]).strip("-_")[:70] or "card"
            output = folder / f"{slug}-themed.png"
            # Reference dimensions also affect memory. Save a bounded working reference,
            # separately from output so Print Setup sees only the edited card.
            reference = self.root / "jobs" / f"{job_id}-reference.png"
            with Image.open(source) as original:
                resized = ImageOps.contain(original, (request.width, request.height), Image.Resampling.LANCZOS)
                resized.save(reference, format="PNG")
            try:
                edit_image(self.assets, reference, output, request.prompt, request.width, request.height,
                           request.steps, request.seed, request.device, cancel, log)
                if cancel.is_set():
                    raise InterruptedError("Cancelled")
                # Validate output before exposing it as a completed job.
                with Image.open(output) as generated:
                    generated.verify()
                _write_json(folder / "generation.json", {
                    **request.model_dump(), "card": card, "source_path": str(source),
                    "output_path": str(output), "engine": "stable-diffusion.cpp",
                    "diffusion_precision": "INT8 convrot", "text_encoder_precision": "Q4_K_M",
                })
                return {"image": _image_data(output), "output_path": str(output),
                        "output_folder": str(folder), "card_id": request.card_id}
            finally:
                reference.unlink(missing_ok=True)

        return self._begin("edit", "Loading Qwen Image 2.1…", work)

    def cancel(self) -> None:
        with self._lock:
            if self._job and self._job["state"] == "running":
                self._cancel.set()
                self._job["message"] = "Cancelling…"

    def release_memory(self) -> None:
        from .editor_session import close_editor_session

        with self._lock:
            if self._job and self._job["state"] == "running":
                raise ValueError("Wait for the current task or cancel it before releasing model memory.")
            close_editor_session()

    def result_path(self, job_id: str) -> Path:
        if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ValueError("No completed image selected.")
        path = self.root / "jobs" / f"{job_id}.json"
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
            output = Path(job["result"]["output_path"]).resolve()
            expected = (self.root / "outputs" / job_id).resolve()
            if job["kind"] != "edit" or job["state"] != "complete" or not output.is_relative_to(expected):
                raise ValueError
            if not output.is_file():
                raise ValueError
            return output
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("The completed image is no longer available.") from exc

    def save_result(self, job_id: str, destination: str) -> str:
        source = self.result_path(job_id)
        target = Path(destination).with_suffix(".png")
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        return str(target)

    def shutdown(self) -> None:
        from .editor_session import close_editor_session

        self.cancel()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        close_editor_session()
