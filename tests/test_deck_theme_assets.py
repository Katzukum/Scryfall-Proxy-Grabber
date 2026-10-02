import hashlib
import io
import json
import os
import threading
import zipfile

import pytest

from src.deck_theme import assets


def fixture_asset(data=b"complete model", path="models/test.bin"):
    return assets.FileAsset(path, "https://example.test/immutable/model", len(data), hashlib.sha256(data).hexdigest())


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}


@pytest.fixture
def manager(tmp_path, monkeypatch):
    result = assets.AssetManager(tmp_path)
    monkeypatch.setattr(result, "_supported", lambda: True)
    return result


def test_status_is_local_and_ignores_unverified_files(manager, monkeypatch):
    monkeypatch.setattr(manager, "_open_url", lambda request: pytest.fail("status must not access network"))
    value = manager.status()
    assert 14_000_000_000 < value["editor"]["total_bytes"] < 14_300_000_000
    assert not value["editor"]["ready"]
    assert value["editor"]["installed_bytes"] == 0
    assert not any("controlnet" in file.path for file in assets.EDITOR_MODEL_FILES)


def test_quantized_editor_manifest_has_all_required_components(manager):
    weights = [file for file in assets.EDITOR_MODEL_FILES if file.path.endswith((".safetensors", ".gguf"))]
    assert len(weights) == 4
    assert sum(file.size for file in weights) == 14_119_107_376
    required_paths = {
        manager.editor_diffusion_model(), manager.editor_text_encoder(),
        manager.editor_vision_projector(), manager.editor_vae(),
    }
    assert required_paths == {manager._path(file.path) for file in weights}
    assert manager.editor_executable().name == "sd-cli.exe"
    assert manager.editor_library().name == "stable-diffusion.dll"
    assert manager.editor_library() in {
        manager._path(file.path) for file in manager._runtime_files("editor")
    }
    assert not any("sd-server" in file.path for file in manager._runtime_files("editor"))
    assert not any("ncnn" in file.url for file in manager._all_files("editor"))


def test_resume_download_uses_range_and_atomically_promotes(manager, monkeypatch):
    data = b"complete model"
    asset = fixture_asset(data)
    partial = manager._path(asset.path + ".part")
    partial.parent.mkdir(parents=True)
    partial.write_bytes(data[:4])
    requests = []

    def respond(request):
        requests.append(request)
        assert not manager._path(asset.path).exists()
        return Response(data[4:], 206, {"Content-Range": f"bytes 4-{len(data)-1}/{len(data)}"})

    monkeypatch.setattr(manager, "_open_url", respond)
    manager._download(asset, threading.Event(), lambda *_: None)
    assert requests[0].get_header("Range") == "bytes=4-"
    assert manager._path(asset.path).read_bytes() == data
    assert not partial.exists()
    assert manager._ready(asset)
    assert assets.AssetManager(manager.root)._ready(asset)


def test_server_ignoring_range_restarts_without_duplicate_bytes(manager, monkeypatch):
    data = b"complete model"
    asset = fixture_asset(data)
    partial = manager._path(asset.path + ".part")
    partial.parent.mkdir(parents=True)
    partial.write_bytes(data[:4])
    monkeypatch.setattr(manager, "_open_url", lambda request: Response(data))
    manager._download(asset, threading.Event(), lambda *_: None)
    assert manager._path(asset.path).read_bytes() == data


def test_early_eof_resumes_on_retry(manager, monkeypatch):
    data = b"complete model"
    asset = fixture_asset(data)
    cancel = threading.Event()
    monkeypatch.setattr(cancel, "wait", lambda _: False)
    responses = iter([Response(data[:4]), Response(data[4:], 206, {"Content-Range": "bytes 4-13/14"})])
    requests = []

    def respond(request):
        requests.append(request)
        return next(responses)

    monkeypatch.setattr(manager, "_open_url", respond)
    manager._download(asset, cancel, lambda *_: None)
    assert requests[1].get_header("Range") == "bytes=4-"
    assert manager._ready(asset)


def test_corrupt_download_never_gets_receipt(manager, monkeypatch):
    asset = fixture_asset()
    cancel = threading.Event()
    monkeypatch.setattr(cancel, "wait", lambda _: False)
    monkeypatch.setattr(manager, "_open_url", lambda request: Response(b"x" * asset.size))
    with pytest.raises(RuntimeError, match="Integrity check failed"):
        manager._download(asset, cancel, lambda *_: None)
    assert not manager._ready(asset)
    assert not manager._path(asset.path).exists()
    assert asset.path not in manager._receipts


def test_cancel_keeps_partial_for_next_setup(manager, monkeypatch):
    data = b"0123456789"
    asset = fixture_asset(data)
    cancel = threading.Event()
    monkeypatch.setattr(assets, "_CHUNK_SIZE", 4)
    monkeypatch.setattr(manager, "_open_url", lambda request: Response(data))

    def progress(done, total, name):
        if done >= 4:
            cancel.set()

    with pytest.raises(InterruptedError):
        manager._download(asset, cancel, progress)
    assert manager._path(asset.path + ".part").read_bytes() == b"0123"
    assert not manager._ready(asset)


def test_modified_verified_file_is_not_ready(manager):
    asset = fixture_asset()
    path = manager._path(asset.path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"complete model")
    manager._record(asset)
    assert manager._ready(asset)
    old = path.stat()
    path.write_bytes(b"x" * asset.size)
    os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns + 1_000_000))
    assert not manager._ready(asset)


def test_git_blob_digest_matches_small_huggingface_files(manager):
    data = b"small configuration\n"
    asset = assets.FileAsset("config.txt", "", len(data), hashlib.sha1(b"blob 20\0" + data).hexdigest(), "git-sha1")
    path = manager._path(asset.path)
    path.write_bytes(data)
    assert manager._verify(path, asset, threading.Event())


def test_archive_only_extracts_verified_allowlisted_entries(manager, monkeypatch):
    data = b"native runtime"
    asset = fixture_asset(data, "runtimes/editor/engine.exe")
    archive = fixture_asset(b"", ".downloads/runtime.zip")
    archive_path = manager._path(archive.path)
    archive_path.parent.mkdir()
    with zipfile.ZipFile(archive_path, "w") as stream:
        stream.writestr("runtime/engine.exe", data)
        stream.writestr("../../outside.txt", b"unexpected payload")
        stream.writestr("runtime/unneeded.exe", b"do not extract")
    monkeypatch.setitem(assets.ARCHIVES, "editor", archive)
    monkeypatch.setitem(assets.ARCHIVE_FILES, "editor", (("runtime/engine.exe", asset),))
    manager._extract_runtime("editor", threading.Event())
    assert manager._ready(asset)
    assert not (manager.root / "runtimes/editor/unneeded.exe").exists()
    assert not (manager.root.parent / "outside.txt").exists()


def test_bundled_runtime_can_be_installed_offline(manager, monkeypatch, tmp_path):
    data = b"native runtime"
    asset = fixture_asset(data, "runtimes/editor/engine.exe")
    license_asset = fixture_asset(b"license", "runtimes/editor/LICENSE")
    bundled = tmp_path / "app-bundle"
    for item, content in ((asset, data), (license_asset, b"license")):
        target = bundled / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    monkeypatch.setitem(assets.ARCHIVE_FILES, "editor", (("engine.exe", asset),))
    monkeypatch.setitem(assets.RUNTIME_LICENSES, "editor", license_asset)
    monkeypatch.setattr(manager, "_bundled_roots", lambda: (bundled,))
    monkeypatch.setattr(manager, "_open_url", lambda request: pytest.fail("bundled runtime must work offline"))
    manager.install_runtime("editor", threading.Event(), lambda *_: None)
    assert manager._ready(asset)
    assert manager._ready(license_asset)


def test_invalid_group_and_platform_fail_before_network(manager, monkeypatch):
    monkeypatch.setattr(manager, "_open_url", lambda request: pytest.fail("must not download"))
    with pytest.raises(ValueError, match="Unknown model group"):
        manager.install("invalid", threading.Event(), lambda *_: None)
    monkeypatch.setattr(manager, "_supported", lambda: False)
    with pytest.raises(RuntimeError, match="Windows x64"):
        manager.install("editor", threading.Event(), lambda *_: None)
    assert not manager.status()["platform_supported"]


def test_invalid_receipt_file_does_not_crash_status(tmp_path):
    (tmp_path / "verified-assets.json").write_text(json.dumps(["invalid receipt structure"]))
    assert not assets.AssetManager(tmp_path).status()["editor"]["ready"]


def test_wrong_resume_range_is_not_appended(manager, monkeypatch):
    data = b"complete model"
    asset = fixture_asset(data)
    partial = manager._path(asset.path + ".part")
    partial.parent.mkdir(parents=True)
    partial.write_bytes(data[:4])
    cancel = threading.Event()
    monkeypatch.setattr(cancel, "wait", lambda _: False)
    responses = iter([
        Response(data[4:], 206, {"Content-Range": "bytes 3-12/14"}),
        Response(data),
    ])
    requests = []

    def respond(request):
        requests.append(request)
        return next(responses)

    monkeypatch.setattr(manager, "_open_url", respond)
    manager._download(asset, cancel, lambda *_: None)
    assert requests[0].get_header("Range") == "bytes=4-"
    assert requests[1].get_header("Range") is None
    assert manager._path(asset.path).read_bytes() == data


def test_same_size_corrupt_runtime_is_never_installed(manager, monkeypatch):
    asset = fixture_asset(b"good binary", "runtimes/editor/engine.exe")
    archive = fixture_asset(b"", ".downloads/runtime.zip")
    archive_path = manager._path(archive.path)
    archive_path.parent.mkdir()
    with zipfile.ZipFile(archive_path, "w") as stream:
        stream.writestr("engine.exe", b"evil binary")
    monkeypatch.setitem(assets.ARCHIVES, "editor", archive)
    monkeypatch.setitem(assets.ARCHIVE_FILES, "editor", (("engine.exe", asset),))
    with pytest.raises(ValueError, match="integrity check failed"):
        manager._extract_runtime("editor", threading.Event())
    assert not manager._path(asset.path).exists()
    assert not manager._ready(asset)


def test_cuda_remains_supplemental_and_status_never_probes_driver(manager, monkeypatch):
    monkeypatch.setattr(manager, "_probe_cuda", lambda: pytest.fail("status must not probe or initialize drivers"))
    mandatory = manager._all_files("editor")
    assert not any("sdcpp-cuda" in asset.path for asset in mandatory)
    assert not any("sd-server" in asset.path for asset in manager._cuda_files())
    assert manager.status()["editor"]["total_bytes"] == sum(asset.size for asset in mandatory)


def test_cuda_selection_is_cached_and_explicit_cpu_stays_portable(manager, monkeypatch):
    probes, installs = [], []
    monkeypatch.setattr(manager, "_probe_cuda", lambda: (probes.append(True) or True, "NVIDIA available"))
    monkeypatch.setattr(manager, "install_editor_cuda_runtime", lambda *_: installs.append(True))
    assert manager.prepare_editor_runtime("auto", threading.Event(), lambda *_: None) == "cuda"
    assert manager.prepare_editor_runtime("auto", threading.Event(), lambda *_: None) == "cuda"
    assert len(probes) == 1
    assert len(installs) == 2
    assert "sdcpp-cuda-3f8527a" in str(manager.editor_executable())
    assert "sdcpp-cuda-3f8527a" in str(manager.editor_library())
    assert manager.prepare_editor_runtime("cpu", threading.Event(), lambda *_: None) == "vulkan"
    assert "sdcpp-cuda-3f8527a" not in str(manager.editor_library("cpu"))


def test_incompatible_driver_skips_cuda_download(manager, monkeypatch):
    monkeypatch.setattr(manager, "_probe_cuda", lambda: (False, "Driver unavailable"))
    monkeypatch.setattr(manager, "install_editor_cuda_runtime", lambda *_: pytest.fail("must not download CUDA"))
    messages = []
    assert manager.prepare_editor_runtime("auto", threading.Event(), lambda *args: messages.append(args[-1])) == "vulkan"
    assert any("Driver unavailable" in message for message in messages)


def test_cuda_setup_failure_falls_back_with_reason_and_no_retry(manager, monkeypatch):
    monkeypatch.setattr(manager, "_probe_cuda", lambda: (True, "NVIDIA available"))
    attempts = []

    def fail(*_):
        attempts.append(True)
        raise RuntimeError("Network unavailable")

    monkeypatch.setattr(manager, "install_editor_cuda_runtime", fail)
    messages = []
    assert manager.prepare_editor_runtime("auto", threading.Event(), lambda *args: messages.append(args[-1])) == "vulkan"
    assert manager.prepare_editor_runtime("auto", threading.Event(), lambda *_: None) == "vulkan"
    assert len(attempts) == 1
    assert any("Network unavailable" in message for message in messages)
    assert "sdcpp-cuda-3f8527a" not in str(manager.editor_executable())


def test_cuda_cancellation_propagates_without_disabling_future_setup(manager, monkeypatch):
    monkeypatch.setattr(manager, "_probe_cuda", lambda: (True, "NVIDIA available"))

    def cancel(*_):
        raise InterruptedError("cancelled")

    monkeypatch.setattr(manager, "install_editor_cuda_runtime", cancel)
    with pytest.raises(InterruptedError):
        manager.prepare_editor_runtime("auto", threading.Event(), lambda *_: None)
    assert not manager._editor_cuda_failure


def test_cuda_startup_failure_switches_getters_to_vulkan(manager, monkeypatch):
    monkeypatch.setattr(manager, "_probe_cuda", lambda: (True, "NVIDIA available"))
    monkeypatch.setattr(manager, "install_editor_cuda_runtime", lambda *_: None)
    manager.prepare_editor_runtime("auto", threading.Event(), lambda *_: None)
    manager.mark_editor_cuda_unavailable("Native DLL failed to load")
    assert "sdcpp-cuda-3f8527a" not in str(manager.editor_library())
    assert manager.prepare_editor_runtime("auto", threading.Event(), lambda *_: None) == "vulkan"


def test_cuda_runtime_reuses_bundled_files_without_network(manager, monkeypatch, tmp_path):
    data = b"cuda library"
    asset = fixture_asset(data, "runtimes/sdcpp-cuda-3f8527a/ggml-cuda.dll")
    archive = fixture_asset(b"unused", ".downloads/cuda/runtime.zip")
    bundled = tmp_path / "bundle"
    source = bundled / asset.path
    source.parent.mkdir(parents=True)
    source.write_bytes(data)
    monkeypatch.setattr(assets, "CUDA_ARCHIVES", (archive,))
    monkeypatch.setattr(assets, "CUDA_ARCHIVE_FILES", {archive.path: (("ggml-cuda.dll", asset),)})
    monkeypatch.setattr(assets, "CUDA_RUNTIME_LICENSES", ())
    monkeypatch.setattr(manager, "_bundled_roots", lambda: (bundled,))
    monkeypatch.setattr(manager, "_open_url", lambda *_: pytest.fail("local CUDA reuse should not download"))
    manager.install_editor_cuda_runtime(threading.Event(), lambda *_: None)
    assert manager._ready(asset)


@pytest.mark.parametrize("version,capability,expected", [(12070, (8, 9), False), (12080, (7, 0), False),
                                                      (12080, (7, 5), True), (13000, (8, 9), True)])
def test_native_cuda_probe_checks_driver_and_compute_capability(manager, monkeypatch, version, capability, expected):
    def output(pointer, value):
        pointer._obj.value = value
        return 0

    class Driver:
        pass

    driver = Driver()
    driver.cuInit = lambda _: 0
    driver.cuDriverGetVersion = lambda pointer: output(pointer, version)
    driver.cuDeviceGetCount = lambda pointer: output(pointer, 1)
    driver.cuDeviceGet = lambda pointer, index: output(pointer, index)
    driver.cuDeviceComputeCapability = lambda major, minor, device: (
        output(major, capability[0]) or output(minor, capability[1])
    )
    calls = []

    def load(name, *, winmode):
        calls.append((name, winmode))
        return driver

    monkeypatch.setattr(assets.ctypes, "WinDLL", load, raising=False)
    assert manager._probe_cuda()[0] is expected
    assert calls == [("nvcuda.dll", 0x00000800)]
