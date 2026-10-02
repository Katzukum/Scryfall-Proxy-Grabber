import io
import json
import os
import ctypes
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

from PIL import Image
import pytest

from src.deck_theme.editor_session import EditorSession, EditorStartupError
from src.deck_theme.engine import InferenceCancelled, InferenceError
from src.deck_theme.native_abi import PINNED_COMMIT, create_ffi
from src.deck_theme.native_worker import MAX_MESSAGE_BYTES, run_protocol
from src.deck_theme import editor_session


class FakeAssets:
    def __init__(self, root):
        self.root = root
        for name in ("gpu.dll", "cpu.dll", "diffusion", "encoder", "vision", "vae"):
            (root / name).write_bytes(b"verified test asset")

    def editor_library(self, device):
        return self.root / ("cpu.dll" if device == "cpu" else "gpu.dll")

    def editor_diffusion_model(self):
        return self.root / "diffusion"

    def editor_text_encoder(self):
        return self.root / "encoder"

    def editor_vision_projector(self):
        return self.root / "vision"

    def editor_vae(self):
        return self.root / "vae"


class FakeWorker:
    def __init__(self, action=None):
        self.responses = queue.Queue()
        self.commands = []
        self.closed = False
        self.tail = []
        self.process = SimpleNamespace(poll=lambda: 0 if self.closed else None)
        self.action = action
        self.close_event = threading.Event()

    def drain(self, on_log):
        pass

    def send(self, command):
        self.commands.append(command)
        if self.action and self.action(self, command):
            return
        if command["op"] == "init":
            self.responses.put({"id": command["id"], "event": "ready", "commit": PINNED_COMMIT})
        else:
            Image.new("RGB", (command["width"], command["height"]), "green").save(command["output"])
            self.responses.put({"id": command["id"], "event": "complete"})

    def close(self):
        self.closed = True
        self.close_event.set()


@pytest.fixture
def setup(tmp_path):
    assets = FakeAssets(tmp_path)
    source = tmp_path / "source.png"
    Image.new("RGB", (64, 96), "red").save(source)
    workers = []

    def factory():
        worker = FakeWorker()
        workers.append(worker)
        return worker

    session = EditorSession(factory, idle_seconds=30, startup_seconds=0.5, generation_seconds=0.5)
    yield assets, source, session, workers
    session.close()


def edit(setup, tmp_path, *, device="auto", cancel=None, name="result.png"):
    assets, source, session, _ = setup
    destination = tmp_path / name
    session.edit(assets, source, destination, "Portal ring", 64, 96, 25, 42,
                 device, cancel or threading.Event(), lambda _message: None)
    return destination


def test_session_reuses_context_for_repeated_edits_and_publishes_png(setup, tmp_path):
    first = edit(setup, tmp_path)
    second = edit(setup, tmp_path, name="second.png")
    workers = setup[3]
    assert len(workers) == 1
    assert [command["op"] for command in workers[0].commands] == ["init", "edit", "edit"]
    assert not workers[0].closed
    for path in (first, second):
        with Image.open(path) as generated:
            assert generated.size == (64, 96) and generated.format == "PNG"
    assert not list(tmp_path.glob(".result.*.png"))


def test_device_change_closes_previous_context(setup, tmp_path):
    edit(setup, tmp_path)
    edit(setup, tmp_path, device="cpu")
    first, second = setup[3]
    assert first.closed and not second.closed
    assert second.commands[0]["device"] == "cpu"
    assert second.commands[0]["library"].endswith("cpu.dll")


def test_modified_model_restarts_context(setup, tmp_path):
    edit(setup, tmp_path)
    setup[0].editor_vae().write_bytes(b"different model bytes")
    edit(setup, tmp_path)
    assert len(setup[3]) == 2 and setup[3][0].closed


def test_no_resubmission_after_an_uncertain_send(setup, tmp_path):
    edit(setup, tmp_path)
    worker = setup[3][0]

    def lose_response(_worker, command):
        if command["op"] == "edit":
            raise BrokenPipeError("response lost after accepting the request")

    worker.action = lose_response
    with pytest.raises(BrokenPipeError):
        edit(setup, tmp_path, name="new.png")
    assert worker.closed
    assert len([command for command in worker.commands if command["op"] == "edit"]) == 2
    assert len(setup[3]) == 1 and not (tmp_path / "new.png").exists()


def test_cancellation_kills_worker_and_never_publishes_output(setup, tmp_path):
    edit(setup, tmp_path)
    worker = setup[3][0]
    cancel = threading.Event()

    def cancel_generation(_worker, command):
        if command["op"] == "edit":
            Image.new("RGB", (64, 96)).save(command["output"])
            cancel.set()
            return True

    worker.action = cancel_generation
    with pytest.raises(InferenceCancelled):
        edit(setup, tmp_path, cancel=cancel, name="cancelled.png")
    assert worker.closed and not (tmp_path / "cancelled.png").exists()
    assert not list(tmp_path.glob(".cancelled.*.png"))


def test_wrong_image_size_preserves_existing_output_and_discards_context(setup, tmp_path):
    original = edit(setup, tmp_path)
    content = original.read_bytes()
    worker = setup[3][0]

    def wrong_shape(owned, command):
        Image.new("RGB", (32, 32)).save(command["output"])
        owned.responses.put({"id": command["id"], "event": "complete"})
        return True

    worker.action = wrong_shape
    with pytest.raises(InferenceError, match="size"):
        edit(setup, tmp_path)
    assert worker.closed and original.read_bytes() == content


def test_idle_timer_releases_native_memory(setup, tmp_path):
    setup[2]._idle_seconds = 0.025
    edit(setup, tmp_path)
    assert setup[3][0].close_event.wait(1)
    edit(setup, tmp_path)
    assert len(setup[3]) == 2


def test_explicit_close_and_stale_idle_timer_do_not_close_new_worker(setup, tmp_path):
    edit(setup, tmp_path)
    first = setup[3][0]
    setup[2].close()
    edit(setup, tmp_path)
    setup[2]._idle_close(first)
    assert first.closed and not setup[3][1].closed


def test_mismatched_native_version_is_startup_only_failure(setup, tmp_path):
    worker = FakeWorker(lambda owned, command: owned.responses.put({
        "id": command["id"], "event": "ready", "commit": "wrong-version",
    }) or True)
    setup[2]._factory = lambda: worker
    with pytest.raises(EditorStartupError, match="version"):
        edit(setup, tmp_path)
    assert worker.closed and [command["op"] for command in worker.commands] == ["init"]


def test_generation_failure_is_not_retriable_startup_failure(setup, tmp_path):
    edit(setup, tmp_path)
    worker = setup[3][0]
    worker.action = lambda owned, command: owned.responses.put({
        "id": command["id"], "event": "error", "message": "GPU allocation failed",
    }) or True
    with pytest.raises(InferenceError) as captured:
        edit(setup, tmp_path)
    assert not isinstance(captured.value, EditorStartupError)
    assert worker.closed


def test_stale_response_cannot_complete_another_request(setup, tmp_path):
    edit(setup, tmp_path)
    worker = setup[3][0]
    worker.action = lambda owned, _command: owned.responses.put({"id": "old-request", "event": "complete"}) or True
    with pytest.raises(InferenceError, match="invalid response"):
        edit(setup, tmp_path)
    assert worker.closed


def test_protocol_reuses_editor_and_frees_it_on_eof():
    instances = []

    class Editor:
        def __init__(self, command, log):
            self.edits = []
            self.closed = False
            instances.append(self)

        def edit(self, command):
            self.edits.append(command)

        def close(self):
            self.closed = True

    commands = [{"id": "init", "op": "init"}, {"id": "one", "op": "edit"}, {"id": "two", "op": "edit"}]
    source = io.BytesIO(b"".join(json.dumps(command).encode() + b"\n" for command in commands))
    output = io.BytesIO()
    assert run_protocol(source, output, lambda _: None, Editor) == 0
    assert len(instances) == 1 and len(instances[0].edits) == 2 and instances[0].closed
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [response["event"] for response in responses] == ["ready", "complete", "complete"]


def test_protocol_rejects_oversized_messages_without_initializing_models():
    output = io.BytesIO()
    assert run_protocol(io.BytesIO(b"x" * (MAX_MESSAGE_BYTES + 1)), output, lambda _: None,
                        lambda *_: pytest.fail("Must not load models")) == 1
    assert json.loads(output.getvalue())["event"] == "error"


def test_pinned_ffi_layout_has_expected_x64_sizes():
    ffi = create_ffi()
    assert ffi.sizeof("sd_ctx_params_t") == 320
    assert ffi.sizeof("sd_img_gen_params_t") == 552
    assert ffi.sizeof("sd_image_t") == 24


@pytest.mark.parametrize("windowed", [False, True])
def test_real_worker_entry_uses_only_inherited_pipes_without_loading_models(windowed):
    project_root = Path(__file__).resolve().parents[1]
    executable = Path(sys.executable).with_name("pythonw.exe") if windowed else Path(sys.executable)
    if windowed and (os.name != "nt" or not executable.is_file()):
        pytest.skip("Windows windowed interpreter is unavailable")
    result = subprocess.run(
        [str(executable), str(project_root / "main.py"), "--deck-theme-worker"],
        input=b'{"id":"check","op":"init","device":"invalid"}\n',
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, cwd=project_root,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert result.returncode == 1
    response = json.loads(result.stdout)
    assert response["id"] == "check" and response["event"] == "error"
    assert response["stage"] == "startup" and "device" in response["message"]


def test_native_stdout_cannot_contaminate_the_private_protocol():
    project_root = Path(__file__).resolve().parents[1]
    script = (
        "import os; from src.deck_theme.native_worker import _private_streams; "
        "reader,writer,errors=_private_streams(); "
        "os.write(1,b'native log\\n'); writer.write(b'protocol\\n'); "
        "errors.write(b'worker log\\n')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], input=b"", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=15, cwd=project_root, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert result.returncode == 0 and result.stdout == b"protocol\n"
    assert b"native log" in result.stderr and b"worker log" in result.stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object ownership")
def test_closing_worker_kills_descendants_holding_inherited_pipes(monkeypatch):
    # This reproduces a venv redirector/onefile bootloader tree, without loading
    # a model. The descendant inherits pipes that would keep readers blocked
    # after terminating only the Popen process.
    script = (
        "import subprocess,sys,json,time; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        "print(json.dumps({'id':'tree','event':'spawned','pid':child.pid}),flush=True); "
        "time.sleep(60)"
    )
    monkeypatch.setattr(editor_session, "_worker_command", lambda: [sys.executable, "-u", "-c", script])
    worker = editor_session._Worker()
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    api.OpenProcess.restype = ctypes.c_void_p
    api.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    api.WaitForSingleObject.restype = ctypes.c_uint32
    api.CloseHandle.argtypes = [ctypes.c_void_p]
    api.CloseHandle.restype = ctypes.c_int
    descendant = None
    try:
        message = worker.responses.get(timeout=10)
        assert message["event"] == "spawned"
        descendant = api.OpenProcess(0x00100000, False, message["pid"])  # SYNCHRONIZE
        assert descendant
        assert api.WaitForSingleObject(descendant, 0) == 258  # WAIT_TIMEOUT, still alive
        started = time.monotonic()
        worker.close()
        assert time.monotonic() - started < 5
        assert api.WaitForSingleObject(descendant, 2000) == 0
        assert worker.process.poll() is not None
        assert all(not reader.is_alive() for reader in worker.readers)
    finally:
        worker.close()
        if descendant:
            api.CloseHandle(descendant)


@pytest.mark.skipif(os.name != "nt", reason="Windows suspended launch ownership")
def test_failed_job_assignment_reaps_suspended_worker(monkeypatch):
    processes = []
    original_popen = editor_session.subprocess.Popen

    def capture(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    def fail_assignment(_tree, _process):
        raise OSError("Simulated process ownership failure")

    monkeypatch.setattr(editor_session.subprocess, "Popen", capture)
    monkeypatch.setattr(editor_session.WorkerProcessTree, "attach", fail_assignment)
    with pytest.raises(OSError, match="ownership"):
        editor_session._Worker()
    assert len(processes) == 1 and processes[0].poll() is not None
    assert processes[0].stdin.closed and processes[0].stdout.closed and processes[0].stderr.closed
