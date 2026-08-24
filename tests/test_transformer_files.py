import asyncio
from unittest.mock import patch

from src.downloader import scryfall_client
from src.transformer_files import (
    build_transformer_face_filename,
    build_transformer_group_id,
    collect_transformer_pairs,
)


def test_collect_transformer_pairs_respects_face_index_and_copy_order():
    first_group = build_transformer_group_id("sld", "1675", 1)
    second_group = build_transformer_group_id("sld", "1675", 2)

    front_1 = f"C:/pairs/{build_transformer_face_filename('African Swallow', first_group, 1)}"
    back_1 = f"C:/pairs/{build_transformer_face_filename('African Swallow', first_group, 2)}"
    front_2 = f"C:/pairs/{build_transformer_face_filename('African Swallow', second_group, 1)}"
    back_2 = f"C:/pairs/{build_transformer_face_filename('African Swallow', second_group, 2)}"

    with patch(
        "src.transformer_files.get_transformer_image_paths",
        return_value=[back_2, front_2, back_1, front_1],
    ):
        assert collect_transformer_pairs("ignored") == [
            (front_1, back_1),
            (front_2, back_2),
        ]


def test_process_card_creates_distinct_transformer_files_for_same_face_names():
    class FakeResponse:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        async def get(self, url: str) -> FakeResponse:
            return FakeResponse(url.encode("utf-8"))

    card = {
        "name": "African Swallow / European Swallow",
        "set": "sld",
        "collector_number": "1675",
        "card_faces": [
            {"name": "African Swallow", "image_uris": {"large": "front-image"}},
            {"name": "African Swallow", "image_uris": {"large": "back-image"}},
        ],
    }

    files: dict[str, bytes] = {}

    def fake_write_file(filepath: str, content: bytes) -> None:
        files[filepath] = content

    def fake_copy(source: str, destination: str) -> None:
        files[destination] = files[source]

    async def immediate_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    original_rate = scryfall_client._RATE_LIMIT_SECONDS
    scryfall_client._RATE_LIMIT_SECONDS = 0
    try:
        with (
            patch("src.downloader.scryfall_client.os.makedirs"),
            patch(
                "src.downloader.scryfall_client._write_file",
                side_effect=fake_write_file,
            ),
            patch("src.downloader.scryfall_client.shutil.copy", side_effect=fake_copy),
            patch(
                "src.downloader.scryfall_client.asyncio.to_thread",
                side_effect=immediate_to_thread,
            ),
        ):
            asyncio.run(scryfall_client._process_card(FakeClient(), card, 2, "order", lambda *_: None))
    finally:
        scryfall_client._RATE_LIMIT_SECONDS = original_rate

    created_files = sorted(path.split("/")[-1].split("\\")[-1] for path in files)

    assert created_files == [
        "African_Swallow_face_1--sld_1675_copy_1--1.png",
        "African_Swallow_face_1--sld_1675_copy_2--1.png",
        "African_Swallow_face_2--sld_1675_copy_1--2.png",
        "African_Swallow_face_2--sld_1675_copy_2--2.png",
    ]

    assert files["order\\transformers\\African_Swallow_face_1--sld_1675_copy_1--1.png"] == b"front-image"
    assert files["order\\transformers\\African_Swallow_face_2--sld_1675_copy_1--2.png"] == b"back-image"
    assert files["order\\transformers\\African_Swallow_face_1--sld_1675_copy_2--1.png"] == b"front-image"
    assert files["order\\transformers\\African_Swallow_face_2--sld_1675_copy_2--2.png"] == b"back-image"


def test_process_card_uses_top_level_image_for_adventure_card():
    class FakeResponse:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        async def get(self, url: str) -> FakeResponse:
            return FakeResponse(url.encode("utf-8"))

    card = {
        "name": "Bilbo Baggins, Burglar // Take a Glance",
        "layout": "adventure",
        "set": "hob",
        "collector_number": "34",
        "image_uris": {"large": "combined-image"},
        "card_faces": [
            {"name": "Bilbo Baggins, Burglar", "image_uris": None},
            {"name": "Take a Glance", "image_uris": None},
        ],
    }

    files: dict[str, bytes] = {}

    def fake_write_file(filepath: str, content: bytes) -> None:
        files[filepath] = content

    def fake_copy(source: str, destination: str) -> None:
        files[destination] = files[source]

    async def immediate_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    original_rate = scryfall_client._RATE_LIMIT_SECONDS
    scryfall_client._RATE_LIMIT_SECONDS = 0
    try:
        with (
            patch(
                "src.downloader.scryfall_client._write_file",
                side_effect=fake_write_file,
            ),
            patch("src.downloader.scryfall_client.shutil.copy", side_effect=fake_copy),
            patch(
                "src.downloader.scryfall_client.asyncio.to_thread",
                side_effect=immediate_to_thread,
            ),
        ):
            asyncio.run(scryfall_client._process_card(FakeClient(), card, 2, "order", lambda *_: None))
    finally:
        scryfall_client._RATE_LIMIT_SECONDS = original_rate

    assert files == {
        "order\\Bilbo_Baggins_Burglar__Take_a_Glance--hob_34--1.png": b"combined-image",
        "order\\Bilbo_Baggins_Burglar__Take_a_Glance_hob_34_2.png": b"combined-image",
    }
