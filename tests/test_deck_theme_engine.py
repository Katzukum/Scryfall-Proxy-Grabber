import asyncio
import io
import json
import os
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace

import httpx
from PIL import Image
import pytest

from src.deck_theme import engine


class FakeAssets:
    def __init__(self, root):
        self.root = root
        for name in (
            "editor", "enhancer", "model.gguf", "vision.gguf", "system.txt",
            "qwen_image_2.1_int8_convrot.safetensors", "Qwen3VL-Q4.gguf", "mmproj.gguf", "qwen21-vae.safetensors",
        ):
            (root / name).write_text("system instructions", encoding="utf-8")

    def editor_executable(self):
        return self.root / "editor"

    def editor_diffusion_model(self):
        return self.root / "qwen_image_2.1_int8_convrot.safetensors"

    def editor_text_encoder(self):
        return self.root / "Qwen3VL-Q4.gguf"

    def editor_vision_projector(self):
        return self.root / "mmproj.gguf"

    def editor_vae(self):
        return self.root / "qwen21-vae.safetensors"

    def enhancer_executable(self):
        return self.root / "enhancer"

    def enhancer_model(self):
        return self.root / "model.gguf"

    def enhancer_projector(self):
        return self.root / "vision.gguf"

    def enhancer_system_prompt(self):
        return self.root / "system.txt"


class FakeProcess:
    def __init__(self, returncode=None, output=b""):
        self.returncode = returncode
        self.stdout = io.BytesIO(output)
        self.terminated = False
        self.killed = False
        self.waited = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        self.waited = True
        return self.returncode


@pytest.fixture
def assets(tmp_path):
    return FakeAssets(tmp_path)


@pytest.fixture
def reference(tmp_path):
    path = tmp_path / "original card.png"
    Image.new("RGB", (128, 192), "red").save(path)
    return path


@pytest.mark.parametrize("wrapper", [
    '{"rewritten_prompt": "A green portal ring.", "ratio_follow": "<image1>"}',
    '<think>Inspect the ring.</think>\n{"rewritten_prompt": "A green portal ring."}',
    '```json\n{"rewritten_prompt": "A green portal ring."}\n```',
    'Here is the result:\n{"rewritten_prompt": "A green portal ring."}',
])
def test_complete_prompt_is_extracted(wrapper):
    assert engine.parse_enhanced_prompt(wrapper) == "A green portal ring."


@pytest.mark.parametrize("content", [
    "", "A green portal ring.", '<think>{"rewritten_prompt":"uncompleted thought"}',
    '{"rewritten_prompt":"unfinished', '{"rewritten_prompt": ""}',
    '{"rewritten_prompt": 123}', '{"other":"value"}',
    '{"rewritten_prompt":"example"} {"rewritten_prompt":"answer"}',
    '{"rewritten_prompt":"answer"} extra text',
])
def test_invalid_or_partial_prompt_is_never_sent_to_editor(content):
    with pytest.raises(engine.InferenceError):
        engine.parse_enhanced_prompt(content)


@pytest.mark.parametrize("device", ["auto", "cpu"])
def test_editor_uses_literal_arguments_and_publishes_verified_image(assets, reference, tmp_path, monkeypatch, device):
    captured = {}
    child = FakeProcess(returncode=0)
    prompt = 'Sol Ring & $(throw "bad"); `anything` "Rick and Morty"'

    def launch(argv, **kwargs):
        captured.update(argv=argv, kwargs=kwargs)
        Image.new("RGBA", (128, 192), "blue").save(argv[argv.index("--output") + 1])
        return child

    monkeypatch.setattr(engine.subprocess, "Popen", launch)
    output = tmp_path / "final.png"
    engine.edit_image(assets, reference, output, prompt, 128, 192, 20, 42, device, threading.Event(), lambda _: None)
    argv = captured["argv"]
    assert argv[argv.index("--prompt") + 1] == prompt
    assert argv[argv.index("--width") + 1] == "128"
    assert argv[argv.index("--height") + 1] == "192"
    assert argv[argv.index("--steps") + 1] == "20"
    assert argv[argv.index("--seed") + 1] == "42"
    assert argv[argv.index("--ref-image") + 1] == str(reference.resolve())
    for flag, file in [
        ("--diffusion-model", assets.editor_diffusion_model()), ("--llm", assets.editor_text_encoder()),
        ("--llm_vision", assets.editor_vision_projector()), ("--vae", assets.editor_vae()),
    ]:
        assert argv[argv.index(flag) + 1] == str(file.resolve())
    assert argv[argv.index("--auto-fit") + 1] == "on"
    assert "--fa" in argv
    assert "--offload-to-cpu" not in argv
    assert "--params-backend" not in argv and "--type" not in argv
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["stdin"] == subprocess.DEVNULL
    assert captured["kwargs"]["creationflags"] == (subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if device == "cpu":
        assert argv[argv.index("--backend") + 1] == "cpu"
        assert "--vae-tiling" in argv
    else:
        assert "--backend" not in argv
        assert "--vae-tiling" not in argv
    assert child.waited and child.stdout.closed
    with Image.open(output) as image:
        assert image.getpixel((0, 0)) == (0, 0, 255, 255)
    assert list(tmp_path.glob(".final.*.png")) == []


def test_invalid_native_output_does_not_replace_existing_image(assets, reference, tmp_path, monkeypatch):
    output = tmp_path / "final.png"
    output.write_bytes(b"previous user result")

    def launch(argv, **kwargs):
        Path(argv[argv.index("--output") + 1]).write_bytes(b"truncated output")
        return FakeProcess(returncode=0)

    monkeypatch.setattr(engine.subprocess, "Popen", launch)
    with pytest.raises(engine.InferenceError, match="valid output"):
        engine.edit_image(assets, reference, output, "Edit", 128, 192, 20, 42, "auto", threading.Event(), lambda _: None)
    assert output.read_bytes() == b"previous user result"
    assert list(tmp_path.glob(".final.*.png")) == []


def test_cancel_stops_and_reaps_only_owned_editor(assets, reference, tmp_path, monkeypatch):
    cancel = threading.Event()
    child = FakeProcess()

    def launch(argv, **kwargs):
        Path(argv[argv.index("--output") + 1]).write_bytes(b"partial")
        cancel.set()
        return child

    monkeypatch.setattr(engine.subprocess, "Popen", launch)
    with pytest.raises(InterruptedError):
        engine.edit_image(assets, reference, tmp_path / "final.png", "Edit", 128, 192, 20, 42,
                          "auto", cancel, lambda _: None)
    assert child.terminated and child.waited and child.stdout.closed
    assert list(tmp_path.glob(".final.*.png")) == []
    assert not (tmp_path / "final.png").exists()


@pytest.mark.parametrize("device", ["auto", "cpu"])
def test_enhancer_honors_device_and_is_private_and_unloaded(assets, reference, monkeypatch, device):
    captured = {}
    child = FakeProcess()
    monkeypatch.setenv("LLAMA_ARG_TOOLS", "all")

    def launch(argv, **kwargs):
        captured.update(argv=argv, kwargs=kwargs)
        return child

    async def request(runtime, port, api_key, alias, payload, cancel):
        captured["payload"] = payload
        assert payload["model"] == alias
        assert api_key
        return "A glowing green ring."

    monkeypatch.setattr(engine.subprocess, "Popen", launch)
    monkeypatch.setattr(engine, "_enhancer_request", request)
    assert engine.enhance_prompt(assets, reference, "Use the theme", device, threading.Event(), lambda _: None) == (
        "A glowing green ring."
    )
    argv = captured["argv"]
    assert argv[argv.index("--host") + 1] == "127.0.0.1"
    if device == "cpu":
        assert argv[argv.index("--n-gpu-layers") + 1] == "0"
        assert argv[argv.index("--device") + 1] == "none"
        assert "--no-mmproj-offload" in argv
    else:
        assert argv[argv.index("--n-gpu-layers") + 1] == "auto"
        assert argv[argv.index("--fit") + 1] == "on"
        assert "--mmproj-offload" in argv
        assert "--no-mmproj-offload" not in argv and "--device" not in argv
    assert argv[argv.index("--reasoning-budget") + 1] == "1024"
    assert captured["payload"]["max_tokens"] == 4096
    assert captured["payload"]["chat_template_kwargs"]["enable_thinking"] is True
    assert "LLAMA_ARG_TOOLS" not in captured["kwargs"]["env"]
    assert captured["payload"]["messages"][1]["content"][0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert child.terminated and child.waited


def test_cancel_interrupts_pending_http_generation(monkeypatch):
    cancel = threading.Event()
    cancelled_request = []

    async def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "owned-model"}]})
        asyncio.get_running_loop().call_later(0.01, cancel.set)
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled_request.append(True)
            raise

    client_type = httpx.AsyncClient
    monkeypatch.setattr(engine.httpx, "AsyncClient", lambda **kwargs: client_type(
        **kwargs, transport=httpx.MockTransport(handler),
    ))
    monkeypatch.setattr(engine, "_POLL_SECONDS", 0.005)
    runtime = SimpleNamespace(process=FakeProcess(), drain=lambda: None, on_log=lambda _: None)
    with pytest.raises(engine.InferenceCancelled):
        asyncio.run(engine._enhancer_request(runtime, 9999, "private", "owned-model", {}, cancel))
    assert cancelled_request == [True]


def test_unrelated_loopback_endpoint_never_receives_card(monkeypatch):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(200, json={"data": [{"id": "some-other-model"}]})

    client_type = httpx.AsyncClient
    monkeypatch.setattr(engine.httpx, "AsyncClient", lambda **kwargs: client_type(
        **kwargs, transport=httpx.MockTransport(handler),
    ))
    runtime = SimpleNamespace(process=FakeProcess(), drain=lambda: None, on_log=lambda _: None)
    with pytest.raises(engine.InferenceError, match="private endpoint"):
        asyncio.run(engine._enhancer_request(runtime, 9999, "private", "owned-model", {}, threading.Event()))
    assert paths == ["/health", "/v1/models"]


def test_truncated_http_answer_rejected_even_with_parseable_example(monkeypatch):
    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "owned-model"}]})
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "length", "message": {"content": json.dumps({"rewritten_prompt": "example"})},
        }]})

    client_type = httpx.AsyncClient
    monkeypatch.setattr(engine.httpx, "AsyncClient", lambda **kwargs: client_type(
        **kwargs, transport=httpx.MockTransport(handler),
    ))
    runtime = SimpleNamespace(process=FakeProcess(), drain=lambda: None, on_log=lambda _: None)
    with pytest.raises(engine.InferenceError, match="token limit"):
        asyncio.run(engine._enhancer_request(runtime, 9999, "private", "owned-model", {}, threading.Event()))


def test_successful_enhancement_reports_timing_without_logging_reasoning(monkeypatch):
    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "owned-model"}]})
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps({"rewritten_prompt": "A green portal ring."}),
                "reasoning_content": "Private model reasoning",
            }}],
            "timings": {"predicted_per_second": 47.25},
        })

    client_type = httpx.AsyncClient
    monkeypatch.setattr(engine.httpx, "AsyncClient", lambda **kwargs: client_type(
        **kwargs, transport=httpx.MockTransport(handler),
    ))
    logs = []
    runtime = SimpleNamespace(process=FakeProcess(), drain=lambda: None, on_log=logs.append)
    result = asyncio.run(engine._enhancer_request(runtime, 9999, "private", "owned-model", {}, threading.Event()))
    assert result == "A green portal ring."
    assert "Prompt model ready" in logs[0]
    assert "47.2 tokens/s" in logs[1]
    assert all("Private model reasoning" not in line for line in logs)


def test_runtime_logs_are_bounded_and_strip_terminal_controls(monkeypatch, tmp_path):
    child = FakeProcess(returncode=0, output=b"\x1b[31mred\x1b[0m\x00\n" + b"x" * 100_000)
    monkeypatch.setattr(engine.subprocess, "Popen", lambda *args, **kwargs: child)
    logs = []
    runtime = engine._OwnedProcess([str(tmp_path / "runtime")], logs.append)
    try:
        runtime.reader.join(timeout=1)
        runtime.drain()
        assert logs[0] == "red"
        assert all(len(line) <= engine._MAX_LOG_LINE for line in logs)
        assert len(logs) <= 64
    finally:
        runtime.close()


def test_multiline_prompts_and_private_key_not_copied_to_runtime_logs(monkeypatch, tmp_path):
    child = FakeProcess(returncode=0, output=(
        b"prompt = PRIVATE " + b"x" * 12_000 + b"\nPRIVATE continuation\nnegative-prompt = \n"
        b"output-path = result.png\nsecret-key\nstep 1 of 20\n"
    ))
    monkeypatch.setattr(engine.subprocess, "Popen", lambda *args, **kwargs: child)
    logs = []
    runtime = engine._OwnedProcess([str(tmp_path / "runtime"), "--api-key", "secret-key"], logs.append)
    try:
        runtime.reader.join(timeout=1)
        runtime.drain()
        assert logs == ["output-path = result.png", "[private key]", "step 1 of 20"]
    finally:
        runtime.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows DLL search API")
def test_frozen_dll_directory_restored_even_when_launch_fails(monkeypatch, tmp_path):
    calls = []

    class Function:
        def __init__(self, function):
            self.function = function

        def __call__(self, *args):
            return self.function(*args)

    def get_directory(size, buffer):
        if size:
            buffer.value = str(tmp_path)
        return len(str(tmp_path))

    def set_directory(value):
        calls.append(value)
        return 1

    kernel = SimpleNamespace(GetDllDirectoryW=Function(get_directory), SetDllDirectoryW=Function(set_directory))
    monkeypatch.setattr(engine.ctypes, "WinDLL", lambda *args, **kwargs: kernel)
    monkeypatch.setattr(engine.sys, "frozen", True, raising=False)
    with pytest.raises(OSError):
        with engine._external_dll_search_path():
            assert calls == [None]
            raise OSError("launch failed")
    assert calls == [None, str(tmp_path)]
