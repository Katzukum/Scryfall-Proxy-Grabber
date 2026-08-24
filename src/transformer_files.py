"""Helpers for naming and grouping transformer card image files."""

from __future__ import annotations

import glob
import os
import re


_TRANSFORMER_FILENAME_RE = re.compile(r"^(?P<label>.+?)--(?P<group>.+?)--(?P<face>[12])\.(?P<ext>png|jpg|jpeg|bmp)$", re.IGNORECASE)


def build_transformer_group_id(set_code: str, collector_number: str, copy_index: int) -> str:
    """Build a stable group id for one physical double-faced card copy."""
    return f"{set_code}_{collector_number}_copy_{copy_index}"


def build_transformer_face_filename(face_name: str, group_id: str, face_index: int, extension: str = "png") -> str:
    """Build a transformer face filename with explicit group and face index."""
    if face_index not in (1, 2):
        raise ValueError(f"face_index must be 1 or 2, got {face_index}")

    safe_name = sanitize_filename(face_name)
    return f"{safe_name}_face_{face_index}--{group_id}--{face_index}.{extension}"


def sanitize_filename(name: str) -> str:
    """Remove non-alphanumeric characters from a name for safe filenames."""
    return re.sub(r"[^\w\s]", "", name).strip().replace(" ", "_")


def parse_transformer_filename(path: str) -> tuple[str, int] | None:
    """Extract the transformer group id and face index from a file path."""
    match = _TRANSFORMER_FILENAME_RE.match(os.path.basename(path))
    if not match:
        return None
    return match.group("group"), int(match.group("face"))


def get_transformer_image_paths(folder: str) -> list[str]:
    """Collect and sort all supported image files from a folder."""
    paths: list[str] = []
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
        paths.extend(sorted(glob.glob(os.path.join(folder, ext))))
    return paths


def collect_transformer_pairs(folder: str) -> list[tuple[str, str]]:
    """Return complete transformer face pairs sorted by group id."""
    grouped: dict[str, dict[int, str]] = {}

    for path in get_transformer_image_paths(folder):
        parsed = parse_transformer_filename(path)
        if not parsed:
            continue

        group_id, face_index = parsed
        grouped.setdefault(group_id, {})[face_index] = path

    complete_pairs: list[tuple[str, str]] = []
    for group_id in sorted(grouped):
        faces = grouped[group_id]
        if 1 in faces and 2 in faces:
            complete_pairs.append((faces[1], faces[2]))

    return complete_pairs
