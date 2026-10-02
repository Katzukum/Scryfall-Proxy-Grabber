"""Regressions at the service/engine/private-worker boundaries; no native inference."""

from pathlib import Path
import queue
import threading
from types import SimpleNamespace

from PIL import Image
import pytest

from src.deck_theme import editor_session, engine
from src.deck_theme.native_abi import PINNED_COMMIT
from src.deck_theme.service import DeckThemeService


class RuntimeAssets:
    def __init__(self, root):
        self.root = root
        self.cuda = True
        self.failures = []
        self.events = []
        for name in ("editor.exe", "diffusion", "encoder", "vision", "vae",
                     "cuda/stable-diffusion.dll", "vulkan/stable-diffusion.dll"):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test asset")

    def status(self):
        return {"editor": {"ready": True}, "enhancer": {"ready": True}}

    def editor_executable(self, device="auto"):
        return self.root / "editor.exe"

    def editor_library(self, device="auto"):
        return self.root / ("cuda" if self.cuda and device != "cpu" else "vulkan") / "stable-diffusion.dll"

    def editor_diffusion_model(self):
        return self.root / "diffusion"

    def editor_text_encoder(self):
        return self.root / "encoder"

    def editor_vision_projector(self):
        return self.root / "vision"

    def editor_vae(self):
        return self.root / "vae"

    def mark_editor_cuda_unavailable(self, reason):
        self.failures.append(reason)
        self.cuda = False

    def prepare_editor_runtime(self, device, cancel, progress):
        self.events.append(("prepare", device))
        assert threading.current_thread().name == "DeckTheme-edit"
        return "cuda" if device == "auto" else "vulkan"

    def install(self, group, cancel, progress):
        self.events.append(("install", group))


class PipeWorker:
    def __init__(self, cancel, *, startup_failure=None, edit_failure=None):
        self.cancel = cancel
        self.startup_failure = startup_failure
        self.edit_failure = edit_failure
        self.commands = []
        self.responses = queue.Queue()
        self.tail = []
        self.closed = False
        self.process = SimpleNamespace(poll=lambda: 1 if self.closed else None)

    def drain(self, log):
        pass

    def close(self):
        self.closed = True

    def send(self, command):
        self.commands.append(command)
        if command["op"] == "init":
            if self.startup_failure == "all" or (
                self.startup_failure == "cuda" and Path(command["library"]).parent.name == "cuda"
            ):
                self.responses.put({"id": command["id"], "event": "error", "message": "Native DLL could not initialize"})
            else:
                self.responses.put({"id": command["id"], "event": "ready", "commit": PINNED_COMMIT})
            return
        if self.edit_failure == "lost_ack":
            raise BrokenPipeError("Edit was accepted but its response was lost")
        if self.edit_failure == "cancel":
            self.cancel.set()
            return
        if self.edit_failure == "oom":
            self.responses.put({"id": command["id"], "event": "error", "message": "GPU out of memory"})
            return
        Image.new("RGB", (command["width"], command["height"]), "green").save(command["output"])
        self.responses.put({"id": command["id"], "event": "complete"})


@pytest.fixture
def integration(tmp_path, monkeypatch):
    assets = RuntimeAssets(tmp_path / "assets")
    reference = tmp_path / "reference.png"
    Image.new("RGB", (64, 96), "red").save(reference)
    cancel = threading.Event()
    workers = []
    behavior = {}

    def factory():
        worker = PipeWorker(cancel, **behavior)
        workers.append(worker)
        return worker

    session = editor_session.EditorSession(factory, idle_seconds=30, startup_seconds=1, generation_seconds=1)
    monkeypatch.setattr(editor_session, "_session", session)
    yield SimpleNamespace(assets=assets, reference=reference, cancel=cancel, workers=workers,
                          behavior=behavior, session=session, output=tmp_path / "result.png", logs=[])
    session.close()


def run_edit(case, device="auto"):
    engine.edit_image(case.assets, case.reference, case.output, "Edit the ring", 64, 96, 25, 42,
                      device, case.cancel, case.logs.append)


def test_cuda_startup_failure_falls_back_once_before_submitting_an_edit(integration):
    case = integration
    case.behavior["startup_failure"] = "cuda"
    run_edit(case)
    assert len(case.workers) == 2
    first, fallback = case.workers
    assert first.closed and [command["op"] for command in first.commands] == ["init"]
    assert [command["op"] for command in fallback.commands] == ["init", "edit"]
    assert Path(fallback.commands[0]["library"]).parent.name == "vulkan"
    assert case.assets.failures == ["Native DLL could not initialize"]
    assert sum("retrying with Vulkan" in line for line in case.logs) == 1
    assert case.output.is_file()


def test_fallback_initialization_failure_is_not_retried_again(integration):
    case = integration
    case.behavior["startup_failure"] = "all"
    with pytest.raises(editor_session.EditorStartupError):
        run_edit(case)
    assert len(case.workers) == 2 and all(worker.closed for worker in case.workers)
    assert all([command["op"] for command in worker.commands] == ["init"] for worker in case.workers)
    assert len(case.assets.failures) == 1
    assert not case.output.exists()


@pytest.mark.parametrize("failure,error", [
    ("oom", engine.InferenceError), ("lost_ack", BrokenPipeError), ("cancel", engine.InferenceCancelled),
])
def test_submitted_cuda_edit_never_falls_back_or_repeats(integration, failure, error):
    case = integration
    case.behavior["edit_failure"] = failure
    case.output.write_bytes(b"previous completed image")
    with pytest.raises(error):
        run_edit(case)
    assert len(case.workers) == 1
    assert [command["op"] for command in case.workers[0].commands] == ["init", "edit"]
    assert case.workers[0].closed and case.assets.failures == []
    assert case.output.read_bytes() == b"previous completed image"
    assert not list(case.output.parent.glob(".result.*.png"))


def test_explicit_cpu_initialization_does_not_attempt_cuda_fallback(integration):
    case = integration
    case.behavior["startup_failure"] = "all"
    with pytest.raises(editor_session.EditorStartupError):
        run_edit(case, device="cpu")
    assert len(case.workers) == 1
    assert case.workers[0].commands[0]["device"] == "cpu"
    assert case.assets.failures == []


def make_service(tmp_path):
    assets = RuntimeAssets(tmp_path / "assets")
    service = DeckThemeService(tmp_path / "data", assets=assets)
    source = tmp_path / "card.png"
    Image.new("RGB", (64, 96)).save(source)
    card = service.import_image(str(source))
    return service, assets, card


def finish(service):
    service._thread.join(timeout=5)
    assert not service._thread.is_alive()
    return service.job()


@pytest.mark.parametrize("device", ["auto", "cpu"])
def test_service_prepares_requested_runtime_before_edit(tmp_path, monkeypatch, device):
    service, assets, card = make_service(tmp_path)

    def edit(assets, reference, output, prompt, width, height, steps, seed, requested_device, cancel, log):
        assets.events.append(("edit", requested_device))
        assert cancel is service._cancel
        Image.new("RGB", (width, height)).save(output)

    monkeypatch.setattr(engine, "edit_image", edit)
    service.start_edit({"card_id": card["id"], "theme": "theme", "prompt": "edit", "width": 256,
                        "height": 384, "steps": 25, "seed": 42, "device": device})
    assert finish(service)["state"] == "complete"
    assert assets.events == [("prepare", device), ("edit", device)]


def test_cancelled_runtime_preparation_never_submits_edit(tmp_path, monkeypatch):
    service, assets, card = make_service(tmp_path)

    def cancelled(*_):
        raise InterruptedError("Download cancelled")

    monkeypatch.setattr(assets, "prepare_editor_runtime", cancelled)
    monkeypatch.setattr(engine, "edit_image", lambda *_: assets.events.append(("edit",)))
    service.start_edit({"card_id": card["id"], "theme": "theme", "prompt": "edit", "width": 256,
                        "height": 384, "steps": 25, "seed": 42, "device": "auto"})
    assert finish(service)["state"] == "cancelled"
    assert assets.events == []


@pytest.mark.parametrize("device", ["auto", "cpu"])
def test_service_releases_editor_before_prompt_enhancement(tmp_path, monkeypatch, device):
    service, assets, card = make_service(tmp_path)
    monkeypatch.setattr(editor_session, "close_editor_session", lambda: assets.events.append(("release",)))

    def enhance(assets, reference, prompt, requested_device, cancel, log):
        assets.events.append(("enhance", requested_device))
        return "A themed card."

    monkeypatch.setattr(engine, "enhance_prompt", enhance)
    service.start_enhance(card["id"], "theme", "edit", device)
    assert finish(service)["state"] == "complete"
    assert assets.events == [("release",), ("enhance", device)]


@pytest.mark.parametrize("group", ["editor", "enhancer"])
def test_service_releases_editor_before_model_download(tmp_path, monkeypatch, group):
    service, assets, _ = make_service(tmp_path)
    monkeypatch.setattr(editor_session, "close_editor_session", lambda: assets.events.append(("release",)))
    service.start_download(group)
    assert finish(service)["state"] == "complete"
    assert assets.events == [("release",), ("install", group)]
