"""Private persistent image worker. Communicates only over inherited process pipes."""

from __future__ import annotations

from contextlib import suppress
import ctypes
import json
import os
from pathlib import Path

from PIL import Image

from .native_abi import PINNED_COMMIT, create_ffi

MAX_MESSAGE_BYTES = 64 * 1024


def _integer(value, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Invalid {name}.")
    return value


def _path(value, *, exists: bool = True) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("Invalid local image or model path.")
    result = Path(value).resolve()
    if exists and not result.is_file():
        raise ValueError(f"A required local file is missing: {result.name}")
    return result


class NativeEditor:
    """Retain one pinned model context; all C-owned pixels are freed after each edit."""

    def __init__(self, configuration: dict, log):
        self.ffi = create_ffi()
        self.ctx = self.ffi.NULL
        self._directories = []
        self._strings = []
        self.lib = None
        self.device = configuration.get("device")
        if self.device not in {"auto", "cpu"}:
            raise ValueError("Unknown processing device.")
        library = _path(configuration.get("library"))
        # SetDllDirectory inherited from PyInstaller must not select bundled
        # ggml DLLs belonging to another runtime. This is an isolated child.
        if os.name == "nt":
            ctypes.windll.kernel32.SetDllDirectoryW(None)
            self._directories.append(os.add_dll_directory(str(library.parent)))
        os.chdir(library.parent)
        try:
            self.lib = self.ffi.dlopen(str(library))
            commit = self.ffi.string(self.lib.sd_commit()).decode("ascii", errors="replace")
            if commit != PINNED_COMMIT:
                raise RuntimeError("The native image runtime does not match the pinned ABI version.")

            @self.ffi.callback("sd_log_cb_t")
            def log_callback(level, message, _data):
                try:
                    if level >= self.lib.SD_LOG_INFO and message != self.ffi.NULL:
                        text = self.ffi.string(message, 4096).decode("utf-8", errors="replace")
                        if "prompt" not in text.lower():
                            log(text[:1000])
                except Exception:
                    pass

            @self.ffi.callback("sd_progress_cb_t")
            def progress_callback(step, steps, elapsed, _data):
                with suppress(Exception):
                    log(f"Processing {step}/{steps}")

            self._callbacks = (log_callback, progress_callback)
            self.lib.sd_set_log_callback(log_callback, self.ffi.NULL)
            self.lib.sd_set_progress_callback(progress_callback, self.ffi.NULL)
            parameters = self.ffi.new("sd_ctx_params_t *")
            self.lib.sd_ctx_params_init(parameters)
            for field, key in (
                ("diffusion_model_path", "diffusion"), ("llm_path", "encoder"),
                ("llm_vision_path", "vision"), ("vae_path", "vae"),
            ):
                setattr(parameters, field, self._string(str(_path(configuration.get(key)))))
            parameters.n_threads = max(1, self.lib.sd_get_num_physical_cores())
            parameters.auto_fit = True
            parameters.flash_attn = True
            parameters.conditioning_cache_size = 2
            parameters.tae_preview_only = False
            if self.device == "cpu":
                parameters.backend = self._string("cpu")
            self.ctx = self.lib.new_sd_ctx(parameters)
            if self.ctx == self.ffi.NULL or not self.lib.sd_ctx_supports_image_generation(self.ctx):
                raise RuntimeError("The native runtime could not load an image-editing context.")
        except BaseException:
            self.close()
            raise

    def _string(self, value: str):
        result = self.ffi.new("char[]", value.encode("utf-8"))
        self._strings.append(result)
        return result

    def edit(self, request: dict) -> None:
        width = _integer(request.get("width"), "width", 32, 4096)
        height = _integer(request.get("height"), "height", 32, 4096)
        steps = _integer(request.get("steps"), "steps", 1, 100)
        seed = _integer(request.get("seed"), "seed", 0, 2**32 - 1)
        if width % 32 or height % 32 or width * height > 16_777_216:
            raise ValueError("Unsupported image dimensions.")
        prompt = request.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 16_000 or "\x00" in prompt:
            raise ValueError("Invalid editing prompt.")
        source = _path(request.get("input"))
        output = _path(request.get("output"), exists=False)
        if source == output or output.suffix.lower() != ".png":
            raise ValueError("Invalid output image path.")
        if source.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Reference image exceeds 32 MB.")
        with Image.open(source) as original:
            if original.width * original.height > 32_000_000:
                raise ValueError("Reference image exceeds 32 megapixels.")
            image = original.convert("RGB")
            pixels = self.ffi.new("uint8_t[]", image.tobytes())
            references = self.ffi.new("sd_image_t[]", 1)
            references[0].width, references[0].height = image.size
            references[0].channel, references[0].data = 3, pixels

        parameters = self.ffi.new("sd_img_gen_params_t *")
        self.lib.sd_img_gen_params_init(parameters)
        prompt_buffer = self.ffi.new("char[]", prompt.encode("utf-8"))
        parameters.prompt = prompt_buffer
        parameters.width, parameters.height = width, height
        parameters.seed, parameters.batch_count = seed, 1
        parameters.ref_images, parameters.ref_images_count = references, 1
        parameters.sample_params.sample_method = self.lib.EULER_SAMPLE_METHOD
        parameters.sample_params.scheduler = self.lib.sd_get_default_scheduler(self.ctx, self.lib.EULER_SAMPLE_METHOD)
        parameters.sample_params.sample_steps = steps
        parameters.sample_params.guidance.txt_cfg = 6.0
        parameters.vae_tiling_params.enabled = self.device == "cpu"
        results, count = self.ffi.new("sd_image_t **"), self.ffi.new("int *")
        try:
            if not self.lib.generate_image(self.ctx, parameters, results, count):
                raise RuntimeError("The native image editor failed to generate an image.")
            if results[0] == self.ffi.NULL or count[0] != 1:
                raise RuntimeError("The native image editor returned an unexpected image count.")
            generated = results[0][0]
            if (generated.width, generated.height) != (width, height) or generated.channel not in {3, 4}:
                raise RuntimeError("The native image editor returned an unexpected image shape.")
            if generated.data == self.ffi.NULL:
                raise RuntimeError("The native image editor returned empty pixels.")
            raw = bytes(self.ffi.buffer(generated.data, width * height * generated.channel))
            output.parent.mkdir(parents=True, exist_ok=True)
            Image.frombytes("RGB" if generated.channel == 3 else "RGBA", (width, height), raw).save(output, "PNG")
        finally:
            if results[0] != self.ffi.NULL:
                self.lib.free_sd_images(results[0], count[0])

    def close(self) -> None:
        if self.lib is not None and self.ctx != self.ffi.NULL:
            self.lib.free_sd_ctx(self.ctx)
            self.ctx = self.ffi.NULL
        for directory in self._directories:
            directory.close()
        self._directories.clear()


def run_protocol(input_stream, output_stream, log, editor_factory=NativeEditor) -> int:
    """Handle bounded commands; errors end the worker instead of reusing uncertain state."""
    editor = None
    try:
        while True:
            raw = input_stream.readline(MAX_MESSAGE_BYTES + 1)
            if not raw:
                return 0
            request_id = None
            operation = "init" if editor is None else "edit"
            try:
                if len(raw) > MAX_MESSAGE_BYTES or not raw.endswith(b"\n"):
                    raise ValueError("Worker command exceeds the 64 KB limit or is incomplete.")
                command = json.loads(raw)
                if not isinstance(command, dict) or not isinstance(command.get("id"), str):
                    raise ValueError("Invalid image worker command.")
                request_id = command["id"]
                if len(request_id) > 64:
                    raise ValueError("Invalid image worker request ID.")
                operation = command.get("op")
                if operation == "init" and editor is None:
                    editor = editor_factory(command, log)
                    response = {"id": request_id, "event": "ready", "commit": PINNED_COMMIT}
                elif operation == "edit" and editor is not None:
                    editor.edit(command)
                    response = {"id": request_id, "event": "complete"}
                elif operation == "close":
                    return 0
                else:
                    raise ValueError("Unexpected image worker operation.")
            except Exception as exc:
                response = {"id": request_id, "event": "error", "stage": "startup" if operation == "init" else "edit", "message": str(exc)[:2000]}
                output_stream.write(json.dumps(response).encode("utf-8") + b"\n")
                output_stream.flush()
                return 1
            output_stream.write(json.dumps(response).encode("utf-8") + b"\n")
            output_stream.flush()
    finally:
        if editor is not None:
            editor.close()


def _private_streams():
    """Restore inherited handles in a windowed EXE and keep native stdout off the protocol."""
    if os.name == "nt":
        import msvcrt

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetStdHandle.argtypes = [ctypes.c_ulong]
        kernel.GetStdHandle.restype = ctypes.c_void_p
        kernel.SetStdHandle.argtypes = [ctypes.c_ulong, ctypes.c_void_p]
        kernel.SetStdHandle.restype = ctypes.c_int
        descriptors = []
        for constant, flags in ((-10, os.O_RDONLY), (-11, os.O_WRONLY), (-12, os.O_WRONLY)):
            handle = kernel.GetStdHandle(constant & 0xFFFFFFFF)
            if handle in {None, ctypes.c_void_p(-1).value}:
                raise RuntimeError("The native image worker requires private inherited pipes.")
            descriptors.append(msvcrt.open_osfhandle(handle, flags | os.O_BINARY))
        reader = os.fdopen(os.dup(descriptors[0]), "rb", buffering=0)
        writer = os.fdopen(os.dup(descriptors[1]), "wb", buffering=0)
        errors = os.fdopen(os.dup(descriptors[2]), "wb", buffering=0)
        kernel.SetStdHandle((-11) & 0xFFFFFFFF, msvcrt.get_osfhandle(descriptors[2]))
        os.dup2(descriptors[2], 1)
    else:
        reader = os.fdopen(os.dup(0), "rb", buffering=0)
        writer = os.fdopen(os.dup(1), "wb", buffering=0)
        errors = os.fdopen(os.dup(2), "wb", buffering=0)
        os.dup2(2, 1)
    return reader, writer, errors


def main() -> int:
    reader, writer, errors = _private_streams()

    def log(message: str) -> None:
        text = " ".join(str(message).split())[:1000]
        if text:
            with suppress(OSError):
                errors.write(text.encode("utf-8", errors="replace") + b"\n")

    with reader, writer, errors:
        return run_protocol(reader, writer, log)


if __name__ == "__main__":
    raise SystemExit(main())
