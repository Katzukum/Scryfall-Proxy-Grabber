"""Cancellable local Qwen inference using managed native executables.

Automatic mode lets each native runtime use the GPU. The editor retains an isolated
worker between requests. The service releases it before prompt enhancement so the
stages do not compete for VRAM.
"""

from __future__ import annotations

import asyncio
import base64
from collections import deque
from contextlib import contextmanager, suppress
import ctypes
import io
import json
import os
from pathlib import Path
import queue
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from typing import Callable, Protocol
import uuid

import httpx
from PIL import Image


class InferenceError(RuntimeError):
    """The local runtime could not produce a usable result."""


class InferenceCancelled(InterruptedError):
    """The caller cancelled this inference stage."""


class Assets(Protocol):
    def editor_executable(self) -> Path: ...
    def editor_diffusion_model(self) -> Path: ...
    def editor_text_encoder(self) -> Path: ...
    def editor_vision_projector(self) -> Path: ...
    def editor_vae(self) -> Path: ...
    def enhancer_executable(self) -> Path: ...
    def enhancer_model(self) -> Path: ...
    def enhancer_projector(self) -> Path: ...
    def enhancer_system_prompt(self) -> Path: ...


Log = Callable[[str], None]
_POLL_SECONDS = 0.1
_STARTUP_SECONDS = 300
_ENHANCEMENT_SECONDS = 1800
_MAX_PROMPT_CHARS = 16_000
_MAX_LOG_LINE = 1000
_ENHANCER_THINKING_TOKENS = 1024
_ENHANCER_OUTPUT_TOKENS = 4096
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_SPAWN_LOCK = threading.Lock()


@contextmanager
def _external_dll_search_path():
    """Do not pass PyInstaller's DLL directory to independently built runtimes."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        yield
        return
    # SetDllDirectory is process-wide. Keep the changed interval to CreateProcess
    # only, and restore the original setting even if launching fails.
    with _SPAWN_LOCK:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        get_directory = kernel.GetDllDirectoryW
        get_directory.argtypes = [ctypes.c_ulong, ctypes.c_wchar_p]
        get_directory.restype = ctypes.c_ulong
        set_directory = kernel.SetDllDirectoryW
        set_directory.argtypes = [ctypes.c_wchar_p]
        set_directory.restype = ctypes.c_int
        size = get_directory(0, None)
        buffer = ctypes.create_unicode_buffer(size + 1)
        get_directory(len(buffer), buffer)
        original = buffer.value or None
        if not set_directory(None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            yield
        finally:
            if not set_directory(original):
                raise ctypes.WinError(ctypes.get_last_error())


def _check_cancel(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise InferenceCancelled("Generation cancelled.")


def _validate_device(device: str) -> None:
    if device not in {"auto", "cpu"}:
        raise InferenceError("Device must be 'auto' or 'cpu'.")


def _file(path: Path, description: str) -> Path:
    path = Path(path).resolve()
    if not path.is_file():
        raise InferenceError(f"{description} is missing. Install the local models first.")
    return path


def _validate_prompt(prompt: str) -> str:
    if not isinstance(prompt, str) or not prompt.strip():
        raise InferenceError("An editing instruction is required.")
    if len(prompt) > _MAX_PROMPT_CHARS or "\x00" in prompt:
        raise InferenceError("The editing instruction is too long or contains an invalid character.")
    return prompt.strip()


class _OwnedProcess:
    """Drain bounded output without blocking cancellation on readline()."""

    def __init__(self, argv: list[str], on_log: Log):
        self.on_log = on_log
        self.lines: queue.Queue[str] = queue.Queue(maxsize=64)
        self.tail: deque[str] = deque(maxlen=12)
        self.closed = False
        self.redacting_prompt = False
        self.api_key = argv[argv.index("--api-key") + 1] if "--api-key" in argv else None
        # Ignore ambient llama service settings (tools, downloads, bind address, etc.).
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith("LLAMA_")}
        bundle = getattr(sys, "_MEIPASS", None)
        if getattr(sys, "frozen", False) and bundle:
            bundle_path = Path(bundle).resolve()
            env["PATH"] = os.pathsep.join(
                entry for entry in env.get("PATH", "").split(os.pathsep)
                if entry and not Path(entry).resolve().is_relative_to(bundle_path)
            )
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            with _external_dll_search_path():
                self.process = subprocess.Popen(
                    argv, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, bufsize=0, cwd=str(Path(argv[0]).parent),
                    env=env, creationflags=flags,
                )
        except OSError as exc:
            # Restoring the parent DLL search path can fail after CreateProcess
            # succeeded. Reap that child even though construction is incomplete.
            if hasattr(self, "process"):
                self._stop()
                if self.process.stdout is not None:
                    self.process.stdout.close()
            raise InferenceError(f"Could not start the local runtime: {exc.strerror or type(exc).__name__}") from exc
        self.reader = threading.Thread(target=self._read, name="deck-theme-runtime-output", daemon=True)
        self.reader.start()

    def _enqueue(self, raw: bytes) -> None:
        line = _ANSI.sub("", raw.decode("utf-8", errors="replace"))
        # Suppress native diagnostic prompt echoes, including multiline values.
        # The editor runs at its default INFO level, without verbose prompt dumps.
        if line.startswith("prompt = "):
            self.redacting_prompt = True
        if self.redacting_prompt:
            if line.startswith("output-path = "):
                self.redacting_prompt = False
            else:
                return
        if self.api_key:
            line = line.replace(self.api_key, "[private key]")
        line = "".join(char for char in line if char.isprintable() or char == "\t")[:_MAX_LOG_LINE]
        if not line:
            return
        try:
            self.lines.put_nowait(line)
        except queue.Full:
            # Keeping the most recent diagnostics also bounds noisy native runtimes.
            with suppress(queue.Empty):
                self.lines.get_nowait()
            with suppress(queue.Full):
                self.lines.put_nowait(line)

    def _read(self) -> None:
        pending = b""
        try:
            assert self.process.stdout is not None
            while chunk := self.process.stdout.read(4096):
                pending += chunk.replace(b"\r", b"\n")
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    self._enqueue(line)
                if len(pending) >= 4096:
                    self._enqueue(pending)
                    pending = b""
            if pending:
                self._enqueue(pending)
        except (OSError, ValueError):
            pass  # Closing the owned pipe during cancellation can interrupt reads.

    def drain(self) -> None:
        for _ in range(64):
            try:
                line = self.lines.get_nowait()
            except queue.Empty:
                break
            self.tail.append(line)
            self.on_log(line)

    def failure(self, stage: str) -> InferenceError:
        self.reader.join(timeout=0.2)
        self.drain()
        detail = " | ".join(self.tail)[-2000:]
        return InferenceError(f"{stage} exited with code {self.process.returncode}. {detail}".strip())

    def _stop(self) -> None:
        if self.process.poll() is None:
            with suppress(ProcessLookupError):
                self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        else:
            self.process.wait()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self._stop()
        finally:
            self.reader.join(timeout=1)
            if self.process.stdout is not None:
                self.process.stdout.close()


def _image_data_url(path: Path) -> str:
    if path.stat().st_size > 32 * 1024 * 1024:
        raise InferenceError("The reference image exceeds the 32 MB limit.")
    try:
        with Image.open(path) as source:
            if source.width * source.height > 32_000_000:
                raise InferenceError("The reference image exceeds the 32 megapixel limit.")
            source.load()
            image = source.convert("RGB")
            image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=95)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise InferenceError("The reference image could not be read.") from exc
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def parse_enhanced_prompt(content: str) -> str:
    """Accept complete PE JSON, optionally wrapped in reasoning or a code fence."""
    if not isinstance(content, str) or not content.strip() or len(content) > 128_000:
        raise InferenceError("The prompt enhancer returned an empty or oversized answer.")
    answer = content.strip()
    if "</think>" in answer:
        answer = answer.rsplit("</think>", 1)[1].strip()
    elif "<think>" in answer:
        raise InferenceError("The prompt enhancer stopped before finishing its answer. Retry this card.")
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", answer, flags=re.IGNORECASE)
    if fenced:
        answer = fenced.group(1).strip()
    # Accept a short prose prefix, but never partial JSON, trailing text, or a
    # second object (which may be an example from an unfinished reasoning block).
    start = answer.find("{")
    if start < 0:
        raise InferenceError("The prompt enhancer did not return the expected JSON instruction.")
    try:
        result = json.loads(answer[start:])
    except (json.JSONDecodeError, RecursionError) as exc:
        raise InferenceError("The prompt enhancer returned incomplete or invalid JSON. Retry this card.") from exc
    if not isinstance(result, dict) or not isinstance(result.get("rewritten_prompt"), str):
        raise InferenceError("The prompt enhancer response is missing rewritten_prompt.")
    return _validate_prompt(result["rewritten_prompt"])


async def _enhancer_request(
    runtime: _OwnedProcess, port: int, api_key: str, alias: str, payload: dict, cancel: threading.Event,
) -> str:
    startup_started = time.monotonic()
    timeout = httpx.Timeout(connect=2, read=None, write=30, pool=2)
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{port}", headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout, trust_env=False, follow_redirects=False,
    ) as client:
        deadline = time.monotonic() + _STARTUP_SECONDS
        while True:
            _check_cancel(cancel)
            runtime.drain()
            if runtime.process.poll() is not None:
                raise runtime.failure("Prompt enhancer")
            try:
                health = await client.get("/health", timeout=0.5)
                if health.status_code == 200:
                    # /health is public. Authenticate and verify our unique model
                    # before sending the image in case another process won the port.
                    models = await client.get("/v1/models", timeout=0.5)
                    if models.status_code == 200:
                        entries = models.json().get("data", [])
                        if any(entry.get("id") == alias for entry in entries):
                            break
                    raise InferenceError("The local prompt enhancer could not verify its private endpoint.")
            except httpx.RequestError:
                pass
            if time.monotonic() >= deadline:
                raise InferenceError("The local prompt enhancer did not become ready within five minutes.")
            await asyncio.sleep(_POLL_SECONDS)

        runtime.on_log(f"Prompt model ready in {time.monotonic() - startup_started:.1f}s; analyzing the reference image.")
        request = asyncio.create_task(client.post("/v1/chat/completions", json=payload))
        generation_started = time.monotonic()
        deadline = time.monotonic() + _ENHANCEMENT_SECONDS
        try:
            while not request.done():
                _check_cancel(cancel)
                runtime.drain()
                if runtime.process.poll() is not None:
                    raise runtime.failure("Prompt enhancer")
                if time.monotonic() >= deadline:
                    raise InferenceError("Prompt enhancement exceeded 30 minutes. Retry or use a shorter instruction.")
                await asyncio.sleep(_POLL_SECONDS)
            _check_cancel(cancel)
            response = await request
            if response.status_code != 200:
                raise InferenceError(f"The local prompt enhancer rejected the request (HTTP {response.status_code}).")
            try:
                result = response.json()
                choice = result["choices"][0]
                if choice.get("finish_reason") != "stop":
                    raise InferenceError("Prompt enhancement reached its token limit or stopped early. Retry this card.")
                prompt = parse_enhanced_prompt(choice["message"]["content"])
                elapsed = time.monotonic() - generation_started
                timing = result.get("timings", {})
                speed = timing.get("predicted_per_second") if isinstance(timing, dict) else None
                detail = f" ({speed:.1f} tokens/s)" if isinstance(speed, (int, float)) and speed > 0 else ""
                runtime.on_log(f"Prompt rewritten in {elapsed:.1f}s{detail}.")
                return prompt
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise InferenceError("The local prompt enhancer returned an invalid response.") from exc
        finally:
            if not request.done():
                request.cancel()
            await asyncio.gather(request, return_exceptions=True)


def enhance_prompt(
    assets: Assets, image_path: Path, instruction: str, device: str,
    cancel: threading.Event, on_log: Log,
) -> str:
    """Describe/edit a reference with the dedicated PE-I2I model, then unload it."""
    _check_cancel(cancel)
    _validate_device(device)
    instruction = _validate_prompt(instruction)
    image_path = _file(image_path, "Reference image")
    executable = _file(assets.enhancer_executable(), "Prompt enhancer runtime")
    model = _file(assets.enhancer_model(), "Prompt enhancer model")
    projector = _file(assets.enhancer_projector(), "Prompt enhancer vision model")
    system_path = _file(assets.enhancer_system_prompt(), "Prompt enhancer system prompt")
    system_prompt = system_path.read_text(encoding="utf-8").strip()
    if not system_prompt or len(system_prompt) > 64_000:
        raise InferenceError("The installed prompt enhancer system prompt is invalid.")
    image_url = _image_data_url(image_path)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    api_key = secrets.token_urlsafe(32)
    alias = "deck-theme-" + uuid.uuid4().hex
    argv = [
        str(executable), "--model", str(model), "--mmproj", str(projector),
        "--host", "127.0.0.1", "--port", str(port), "--api-key", api_key, "--alias", alias,
        "--ctx-size", "16384", "--parallel", "1", "--batch-size", "512", "--ubatch-size", "256",
        "--image-max-tokens", "1024", "--flash-attn", "auto",
        "--reasoning-budget", str(_ENHANCER_THINKING_TOKENS),
        "--jinja", "--no-webui", "--no-slots",
    ]
    if device == "cpu":
        argv.extend(["--device", "none", "--n-gpu-layers", "0", "--no-mmproj-offload"])
    else:
        # llama.cpp's fitter includes both model and vision-projector memory.
        # An exact layer count would prevent it adapting to smaller GPUs.
        argv.extend(["--n-gpu-layers", "auto", "--fit", "on", "--mmproj-offload"])
    payload = {
        "model": alias,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": instruction},
            ]},
        ],
        "stream": False, "max_tokens": _ENHANCER_OUTPUT_TOKENS, "temperature": 1.0, "top_k": 20,
        "top_p": 0.95, "min_p": 0.0, "repeat_penalty": 1.0, "presence_penalty": 0.0,
        "chat_template_kwargs": {"enable_thinking": True},
    }
    _check_cancel(cancel)
    on_log("Starting the local prompt enhancer " + (
        "on CPU; CPU inference can take several minutes."
        if device == "cpu" else "with automatic GPU acceleration (Vulkan when available)."
    ))
    runtime = _OwnedProcess(argv, on_log)
    try:
        return asyncio.run(_enhancer_request(runtime, port, api_key, alias, payload, cancel))
    except httpx.HTTPError as exc:
        _check_cancel(cancel)
        raise InferenceError("Communication with the local prompt enhancer failed.") from exc
    finally:
        runtime.close()


def edit_image(
    assets: Assets, input_path: Path, output_path: Path, prompt: str,
    width: int, height: int, steps: int, seed: int, device: str,
    cancel: threading.Event, on_log: Log,
) -> None:
    """Edit using native stable-diffusion.cpp; publish only a decoded PNG."""
    _check_cancel(cancel)
    _validate_device(device)
    prompt = _validate_prompt(prompt)
    if any(type(size) is not int or not 32 <= size <= 4096 or size % 32 for size in (width, height)):
        raise InferenceError("Image editing dimensions must be multiples of 32 between 32 and 4096.")
    if type(steps) is not int or not 1 <= steps <= 100:
        raise InferenceError("Denoising steps must be between 1 and 100.")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise InferenceError("Seed must be an integer between 0 and 4294967295.")
    input_path = _file(input_path, "Reference image")
    executable = _file(assets.editor_executable(), "Image editor runtime")
    diffusion = _file(assets.editor_diffusion_model(), "Qwen Image 2.1 INT8 ConvRot model")
    encoder = _file(assets.editor_text_encoder(), "Qwen3-VL text encoder")
    vision = _file(assets.editor_vision_projector(), "Qwen3-VL vision projector")
    vae = _file(assets.editor_vae(), "Qwen Image 2.1 VAE")
    output_path = Path(output_path).resolve()
    if output_path == input_path:
        raise InferenceError("The generated image must have a different path from the original.")
    if output_path.suffix.lower() != ".png":
        raise InferenceError("Generated images must use a .png output path.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if callable(getattr(assets, "editor_library", None)):
        from .editor_session import EditorStartupError, edit_image as edit_in_session

        try:
            edit_in_session(assets, input_path, output_path, prompt, width, height, steps, seed, device, cancel, on_log)
        except EditorStartupError as exc:
            # Only retry a CUDA initialization failure. A submitted edit, OOM,
            # cancellation, or invalid result must not silently generate again.
            if device == "cpu" or "cuda" not in assets.editor_library(device).parent.name.lower():
                raise
            assets.mark_editor_cuda_unavailable(str(exc))
            on_log(f"NVIDIA runtime could not initialize; retrying with Vulkan: {exc}")
            edit_in_session(assets, input_path, output_path, prompt, width, height, steps, seed, device, cancel, on_log)
        return
    temporary = output_path.with_name(f".{output_path.stem}.{uuid.uuid4().hex}.png")
    argv = [
        str(executable), "--diffusion-model", str(diffusion), "--llm", str(encoder),
        "--llm_vision", str(vision), "--vae", str(vae), "--ref-image", str(input_path),
        "--prompt", prompt, "--output", str(temporary), "--width", str(width), "--height", str(height),
        "--steps", str(steps), "--seed", str(seed), "--cfg-scale", "6.0", "--sampling-method", "euler",
        "--auto-fit", "on", "--fa",
    ]
    if device == "cpu":
        argv += ["--backend", "cpu", "--vae-tiling"]
    # The pinned runtime preserves the ConvRot checkpoint's storage precision.
    # Auto-fit selects the available Vulkan GPU and places weights in VRAM, RAM,
    # or disk as needed. Do not combine it with --offload-to-cpu, whose explicit
    # parameter placement disables auto-fit. Let it accelerate conditioning too;
    # te=cpu defeats automatic GPU placement even when the entire model fits.
    # VAE decoding retries with spatial tiling on allocation failure upstream;
    # unconditional 256px tiles add substantial work on capable GPUs.
    on_log("Starting local INT8 ConvRot image editing on " + (
        "CPU." if device == "cpu" else "the automatically selected device (Vulkan when available)."
    ))
    runtime = None
    try:
        _check_cancel(cancel)
        runtime = _OwnedProcess(argv, on_log)
        while runtime.process.poll() is None:
            _check_cancel(cancel)
            runtime.drain()
            cancel.wait(_POLL_SECONDS)
        _check_cancel(cancel)
        runtime.reader.join(timeout=1)
        runtime.drain()
        if runtime.process.returncode != 0:
            raise runtime.failure("Image editor")
        try:
            with Image.open(temporary) as generated:
                if generated.format != "PNG" or generated.size != (width, height):
                    raise InferenceError("The image editor returned an unexpected image format or size.")
                generated.load()
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise InferenceError("The image editor did not produce a valid output image.") from exc
        _check_cancel(cancel)
        os.replace(temporary, output_path)
    finally:
        if runtime is not None:
            runtime.close()
        temporary.unlink(missing_ok=True)
