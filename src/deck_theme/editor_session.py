"""Own a warm image worker over private inherited pipes, without a network listener."""

from __future__ import annotations

from collections import deque
from contextlib import suppress
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid

from PIL import Image

from .engine import InferenceCancelled, InferenceError, _external_dll_search_path
from .native_abi import PINNED_COMMIT
from .process_tree import WorkerProcessTree

MAX_MESSAGE_BYTES = 64 * 1024


class EditorStartupError(InferenceError):
    """Worker failed before any generation request was sent; another backend may be tried."""


def _worker_command():
    project_root = Path(__file__).resolve().parents[2]
    return [sys.executable, "--deck-theme-worker"] if getattr(sys, "frozen", False) else [
        sys.executable, "-u", str(project_root / "main.py"), "--deck-theme-worker",
    ]


class _Worker:
    def __init__(self):
        project_root = Path(__file__).resolve().parents[2]
        argv = _worker_command()
        self.responses = queue.Queue(maxsize=8)
        self.logs = queue.Queue(maxsize=64)
        self.tail = deque(maxlen=8)
        self.closed = False
        self._close_lock = threading.Lock()
        self._tree = WorkerProcessTree()
        try:
            with _external_dll_search_path():
                self.process = subprocess.Popen(
                    argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    shell=False, bufsize=0, cwd=project_root, **self._tree.popen_options(),
                )
                self._tree.attach(self.process)
        except BaseException:
            # Restoring PyInstaller's DLL search directory can fail after the
            # child started. Do not leak that otherwise-untracked process.
            self._tree.close()
            if hasattr(self, "process"):
                if self.process.poll() is None:
                    self.process.kill()
                self.process.wait(timeout=3)
                for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                    stream.close()
            raise
        self.readers = [
            threading.Thread(target=self._read_responses, name="DeckTheme-worker-responses", daemon=True),
            threading.Thread(target=self._read_logs, name="DeckTheme-worker-logs", daemon=True),
        ]
        try:
            for reader in self.readers:
                reader.start()
        except BaseException:
            self.close()
            raise

    def _put_response(self, message) -> None:
        try:
            self.responses.put_nowait(message)
        except queue.Full:
            # A worker should emit exactly one response per command.
            with suppress(queue.Empty):
                self.responses.get_nowait()
            with suppress(queue.Full):
                self.responses.put_nowait({"event": "protocol_error"})

    def _read_responses(self) -> None:
        try:
            while raw := self.process.stdout.readline(MAX_MESSAGE_BYTES + 1):
                if len(raw) > MAX_MESSAGE_BYTES or not raw.endswith(b"\n"):
                    self._put_response({"event": "protocol_error"})
                    return
                try:
                    message = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    self._put_response({"event": "protocol_error"})
                    return
                self._put_response(message)
        except (OSError, ValueError):
            pass
        finally:
            self._put_response(None)

    def _read_logs(self) -> None:
        pending = b""
        try:
            while chunk := self.process.stderr.read(4096):
                pending += chunk.replace(b"\r", b"\n")
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    self._log_line(line)
                if len(pending) >= 4096:
                    self._log_line(pending[:4096])
                    pending = b""
            if pending:
                self._log_line(pending)
        except (OSError, ValueError):
            pass

    def _log_line(self, raw: bytes) -> None:
        text = "".join(char for char in raw.decode("utf-8", errors="replace") if char.isprintable())[:1000]
        if not text or "prompt" in text.lower():
            return
        try:
            self.logs.put_nowait(text)
        except queue.Full:
            with suppress(queue.Empty):
                self.logs.get_nowait()
            with suppress(queue.Full):
                self.logs.put_nowait(text)

    def drain(self, on_log) -> None:
        for _ in range(64):
            try:
                line = self.logs.get_nowait()
            except queue.Empty:
                return
            self.tail.append(line)
            on_log(line)

    def send(self, command: dict) -> None:
        encoded = json.dumps(command, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > MAX_MESSAGE_BYTES:
            raise InferenceError("The editing request exceeds the worker's 64 KB message limit.")
        self.process.stdin.write(encoded)
        self.process.stdin.flush()

    def close(self) -> None:
        with self._close_lock:
            if self.closed:
                return
            self.closed = True
            self._tree.close()
            if self.process.poll() is None:
                with suppress(OSError):
                    self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
            else:
                self.process.wait()
            for reader in self.readers:
                if reader.ident is not None:
                    reader.join(timeout=1)
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                with suppress(OSError):
                    stream.close()


class EditorSession:
    """One active edit, with a five-minute idle timer for the retained native context."""

    def __init__(self, worker_factory=_Worker, idle_seconds=300, startup_seconds=300, generation_seconds=7200):
        self._factory = worker_factory
        self._idle_seconds = idle_seconds
        self._startup_seconds = startup_seconds
        self._generation_seconds = generation_seconds
        self._lock = threading.RLock()
        self._edit_lock = threading.Lock()
        self._worker = None
        self._key = None
        self._timer = None
        self._active = False

    def _close_if_current(self, worker) -> None:
        with self._lock:
            if self._worker is not worker:
                return
            self._worker = self._key = None
            if self._timer:
                self._timer.cancel()
                self._timer = None
        worker.close()

    def close(self) -> None:
        with self._lock:
            worker = self._worker
        if worker is not None:
            self._close_if_current(worker)

    def _idle_close(self, worker) -> None:
        with self._lock:
            if self._active or self._worker is not worker:
                return
            self._close_if_current(worker)

    def _check(self, worker, cancel) -> None:
        if cancel.is_set():
            raise InferenceCancelled("Image editing cancelled.")
        with self._lock:
            if self._worker is not worker or worker.closed:
                raise InferenceCancelled("The image worker was released.")

    def _wait(self, worker, request_id, event, seconds, cancel, on_log):
        deadline = time.monotonic() + seconds
        while True:
            self._check(worker, cancel)
            worker.drain(on_log)
            if time.monotonic() >= deadline:
                raise InferenceError("The local image worker timed out.")
            try:
                response = worker.responses.get(timeout=0.1)
            except queue.Empty:
                if worker.process.poll() is not None:
                    raise InferenceError("The local image worker stopped. " + " | ".join(worker.tail)[-1800:])
                continue
            if not isinstance(response, dict) or response.get("id") != request_id:
                raise InferenceError("The local image worker returned an invalid response.")
            if response.get("event") == "error":
                raise InferenceError(str(response.get("message") or "Native image editing failed.")[:2000])
            if response.get("event") != event or worker.process.poll() is not None:
                raise InferenceError("The local image worker returned an unexpected response or stopped.")
            self._check(worker, cancel)
            worker.drain(on_log)
            return response

    @staticmethod
    def _configuration(assets, device):
        getters = {
            "library": lambda: assets.editor_library(device),
            "diffusion": assets.editor_diffusion_model, "encoder": assets.editor_text_encoder,
            "vision": assets.editor_vision_projector, "vae": assets.editor_vae,
        }
        configuration = {"device": device}
        stamps = []
        for name, getter in getters.items():
            path = Path(getter()).resolve()
            if not path.is_file():
                raise InferenceError(f"A required image editing file is missing: {path.name}")
            stamp = path.stat()
            configuration[name] = str(path)
            stamps.append((str(path), stamp.st_size, stamp.st_mtime_ns))
        return configuration, (device, *stamps)

    def edit(self, assets, input_path, output_path, prompt, width, height, steps, seed, device, cancel, on_log):
        if not self._edit_lock.acquire(blocking=False):
            raise InferenceError("Another image edit is already running.")
        worker = None
        temporary = None
        try:
            if cancel.is_set():
                self.close()
                raise InferenceCancelled("Image editing cancelled.")
            if device not in {"auto", "cpu"}:
                raise InferenceError("Choose Automatic or CPU processing.")
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 16000 or "\x00" in prompt:
                raise InferenceError("Enter a valid editing prompt of at most 16,000 characters.")
            if any(type(value) is not int or value < 32 or value > 4096 or value % 32 for value in (width, height)):
                raise InferenceError("Image dimensions must be multiples of 32 between 32 and 4096.")
            if type(steps) is not int or not 1 <= steps <= 100 or type(seed) is not int or not 0 <= seed <= 2**32 - 1:
                raise InferenceError("Invalid step count or seed.")
            source, output = Path(input_path).resolve(), Path(output_path).resolve()
            if not source.is_file() or source == output or output.suffix.lower() != ".png":
                raise InferenceError("Choose an existing reference image and a separate PNG output path.")
            configuration, key = self._configuration(assets, device)
            with self._lock:
                self._active = True
                if self._timer:
                    self._timer.cancel()
                    self._timer = None
                if self._worker is not None and (self._key != key or self._worker.process.poll() is not None):
                    self._close_if_current(self._worker)
                worker = self._worker
                if worker is None:
                    try:
                        worker = self._factory()
                    except Exception as exc:
                        raise EditorStartupError(f"Could not start the local image worker: {exc}") from exc
                    self._worker, self._key = worker, key
                    new_worker = True
                else:
                    new_worker = False
            if new_worker:
                on_log("Loading the image editor; its model context will stay ready for the next edit.")
                request_id = uuid.uuid4().hex
                try:
                    worker.send({"id": request_id, "op": "init", **configuration})
                    ready = self._wait(worker, request_id, "ready", self._startup_seconds, cancel, on_log)
                    if ready.get("commit") != PINNED_COMMIT:
                        raise InferenceError("The image worker's native version does not match the pinned runtime.")
                except InferenceCancelled:
                    raise
                except Exception as exc:
                    raise EditorStartupError(str(exc)) from exc
            else:
                on_log("Reusing the loaded image editor.")

            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.png")
            request_id = uuid.uuid4().hex
            self._check(worker, cancel)
            # Never retry this submission: a lost response may still mean the
            # worker accepted generation. Any communication error closes it.
            worker.send({
                "id": request_id, "op": "edit", "input": str(source), "output": str(temporary),
                "prompt": prompt.strip(), "width": width, "height": height, "steps": steps, "seed": seed,
            })
            self._wait(worker, request_id, "complete", self._generation_seconds, cancel, on_log)
            try:
                with Image.open(temporary) as generated:
                    if generated.format != "PNG" or generated.size != (width, height):
                        raise InferenceError("The image editor returned an unexpected image format or size.")
                    generated.load()
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                raise InferenceError("The image editor did not produce a valid PNG image.") from exc
            self._check(worker, cancel)
            os.replace(temporary, output)
            with self._lock:
                self._active = False
                if self._worker is worker:
                    self._timer = threading.Timer(self._idle_seconds, self._idle_close, args=(worker,))
                    self._timer.daemon = True
                    self._timer.start()
        except BaseException:
            if worker is not None:
                self._close_if_current(worker)
            raise
        finally:
            with self._lock:
                self._active = False
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            self._edit_lock.release()


_session = EditorSession()


def edit_image(assets, input_path, output_path, prompt, width, height, steps, seed, device, cancel, on_log):
    return _session.edit(assets, input_path, output_path, prompt, width, height, steps, seed, device, cancel, on_log)


def close_editor_session() -> None:
    _session.close()
