import json
import threading
from pathlib import Path

import pytest
from PIL import Image

from src.deck_theme.service import DeckThemeService, _card_fields


class Assets:
    def status(self):
        return {"editor": {"ready": True}, "enhancer": {"ready": True}}


@pytest.fixture
def service(tmp_path):
    return DeckThemeService(tmp_path / "data", assets=Assets())


def imported_card(service, tmp_path):
    source = tmp_path / "Example.png"
    Image.new("RGB", (1000, 1400), "purple").save(source)
    return service.import_image(str(source))


def wait_finished(service):
    service._thread.join(timeout=5)
    assert not service._thread.is_alive()
    return service.job()


def test_double_faced_card_uses_selected_face_and_rules():
    card = {"name": "Front // Back", "set": "tst", "collector_number": "1", "card_faces": [
        {"name": "Front", "oracle_text": "Front ability", "image_uris": {"png": "https://cards.scryfall.io/front.png"}},
        {"name": "Back", "oracle_text": "Back ability", "image_uris": {"png": "https://cards.scryfall.io/back.png"}},
    ]}
    fields, url = _card_fields(card, 1)
    assert fields["face_name"] == "Back"
    assert fields["oracle_text"] == "Back ability"
    assert url.endswith("back.png")
    with pytest.raises(ValueError):
        _card_fields(card, -1)


def test_combined_card_retains_both_halves():
    fields, _ = _card_fields({"name": "One // Two", "image_uris": {"png": "https://cards.scryfall.io/card.png"},
                             "card_faces": [{"oracle_text": "First"}, {"oracle_text": "Second"}]}, 0)
    assert fields["oracle_text"] == "First // Second"


def test_arbitrary_source_url_rejected():
    with pytest.raises(ValueError, match="Scryfall"):
        _card_fields({"image_uris": {"png": "http://127.0.0.1/private"}}, 0)


def test_import_copies_source_and_prompt_includes_theme(service, tmp_path):
    card = imported_card(service, tmp_path)
    (tmp_path / "Example.png").unlink()
    assert card["image"].startswith("data:image/png;base64,")
    prompt = service.build_prompt(card["id"], "Rick and Morty")
    assert "Rick and Morty" in prompt and "Example" in prompt
    assert "rules text" in prompt
    with pytest.raises(ValueError):
        service.build_prompt("../other", "theme")


def test_one_job_at_a_time_and_cancellation(service):
    started = threading.Event()

    def work(job_id, cancel, progress, log):
        started.set()
        cancel.wait(3)
        progress(1, 2, "Next")

    service._begin("download", "Starting", work)
    assert started.wait(2)
    with pytest.raises(ValueError, match="already running"):
        service._begin("edit", "Second", work)
    service.cancel()
    assert wait_finished(service)["state"] == "cancelled"


def test_edit_keeps_original_out_of_print_folder_and_saves_provenance(service, tmp_path, monkeypatch):
    from src.deck_theme import engine

    card = imported_card(service, tmp_path)

    def fake_edit(assets, reference, output, prompt, width, height, steps, seed, device, cancel, log):
        with Image.open(reference) as image:
            assert image.width <= width and image.height <= height
        Image.new("RGB", (width, height), "green").save(output)

    monkeypatch.setattr(engine, "edit_image", fake_edit)
    options = {"card_id": card["id"], "theme": "theme", "prompt": "edit this card", "width": 512,
               "height": 704, "steps": 25, "seed": 42, "device": "auto"}
    service.start_edit(options)
    job = wait_finished(service)
    assert job["state"] == "complete", job
    folder = Path(job["result"]["output_folder"])
    assert len(list(folder.glob("*.png"))) == 1
    assert job["result"]["card_id"] == card["id"]
    assert json.loads((folder / "generation.json").read_text())["seed"] == 42
    assert service.result_path(job["id"]).is_file()
    copied = tmp_path / "export.png"
    service.save_result(job["id"], str(copied))
    assert copied.read_bytes() == service.result_path(job["id"]).read_bytes()
    assert not list((service.root / "jobs").glob("*-reference.png"))
    options["width"] = 513
    with pytest.raises(ValueError, match="multiples"):
        service.start_edit(options)


def test_failed_edit_does_not_expose_an_output(service, tmp_path, monkeypatch):
    from src.deck_theme import engine

    card = imported_card(service, tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("Insufficient GPU memory")

    monkeypatch.setattr(engine, "edit_image", fail)
    service.start_edit({"card_id": card["id"], "theme": "theme", "prompt": "prompt", "width": 512,
                        "height": 704, "steps": 25, "seed": 42, "device": "auto"})
    job = wait_finished(service)
    assert job["state"] == "failed" and "memory" in job["error"]
    with pytest.raises(ValueError):
        service.result_path(job["id"])


def test_restart_marks_interrupted_job_failed(service):
    service.root.mkdir(parents=True)
    (service.root / "last-job.json").write_text(json.dumps({"id": "a" * 32, "kind": "edit", "state": "running"}))
    reopened = DeckThemeService(service.root, assets=Assets())
    assert reopened.job()["state"] == "failed"


def test_failed_initial_persistence_does_not_block_retry(service, monkeypatch):
    original = service._persist_job

    def disk_full():
        raise OSError("Disk full")

    monkeypatch.setattr(service, "_persist_job", disk_full)
    with pytest.raises(OSError, match="Disk full"):
        service._begin("download", "Starting", lambda *args: {})
    assert service.job()["state"] == "failed"
    assert service._thread is None
    monkeypatch.setattr(service, "_persist_job", original)
    service._begin("download", "Retry", lambda *args: {})
    assert wait_finished(service)["state"] == "complete"
