"""PNG renderer — arranges card images into grid layout on PNG canvases using Pillow."""

import os
from typing import Callable

from PIL import Image, ImageDraw

from src.models import PrintSettings
from src.transformer_files import collect_transformer_pairs, get_transformer_image_paths


LogCallback = Callable[[str, str], None]
ProgressCallback = Callable[[int, int, str], None]

# Default print resolution
DPI = 300


def _noop_log(level: str, message: str) -> None:
    pass


def _noop_progress(current: int, total: int, label: str) -> None:
    pass


def _mm_to_px(mm_val: float, dpi: int = DPI) -> int:
    """Convert millimeters to pixels at the given DPI."""
    return int((mm_val / 25.4) * dpi)


def _create_rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    """Create a rounded rectangle mask for card clipping."""
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0) + size, radius=radius, fill=255)
    return mask


def _get_image_paths(folder: str) -> list[str]:
    """Collect and sort all image files from a folder."""
    return get_transformer_image_paths(folder)


def _compute_grid(
    canvas_w: int, canvas_h: int, card_w: int, card_h: int, padding: int
) -> tuple[list[int], list[int], int, int]:
    """Compute optimal card grid positions centered on the canvas.

    Returns:
        (x_positions, y_positions, cols, rows)
    """
    cols = (canvas_w + padding) // (card_w + padding)
    rows = (canvas_h + padding) // (card_h + padding)

    if cols == 0 or rows == 0:
        raise ValueError(
            f"Canvas ({canvas_w}x{canvas_h}px) is too small for cards ({card_w}x{card_h}px)."
        )

    grid_w = (cols * card_w) + ((cols - 1) * padding)
    grid_h = (rows * card_h) + ((rows - 1) * padding)
    margin_x = (canvas_w - grid_w) // 2
    margin_y = (canvas_h - grid_h) // 2

    x_positions = [margin_x + i * (card_w + padding) for i in range(cols)]
    y_positions = [margin_y + i * (card_h + padding) for i in range(rows)]
    return x_positions, y_positions, cols, rows


def create_proxy_png(
    image_folder: str,
    settings: PrintSettings,
    on_log: LogCallback = _noop_log,
    on_progress: ProgressCallback = _noop_progress,
) -> list[str]:
    """Create single-sided PNG sheets from card images.

    Args:
        image_folder: Path to folder containing card images.
        settings: Print settings (dimensions, padding, etc.).
        on_log: Logging callback.
        on_progress: Progress callback.

    Returns:
        List of paths to created PNG files.
    """
    card_w = _mm_to_px(settings.card_width_mm)
    card_h = _mm_to_px(settings.card_height_mm)
    corner_r = _mm_to_px(settings.corner_radius_mm)
    padding = _mm_to_px(settings.padding_mm)

    # 11 x 8.5 inches at 300 DPI (landscape letter)
    canvas_w = int(11 * DPI)
    canvas_h = int(8.5 * DPI)

    if not os.path.isdir(image_folder):
        on_log("ERROR", f"Folder does not exist: {image_folder}")
        return []

    image_paths = _get_image_paths(image_folder)
    if not image_paths:
        on_log("ERROR", f"No images found in: {image_folder}")
        return []

    on_log("INFO", f"Found {len(image_paths)} images for single-sided PNG sheets.")

    x_positions, y_positions, cols, rows = _compute_grid(canvas_w, canvas_h, card_w, card_h, padding)
    cards_per_page = cols * rows
    output_paths: list[str] = []
    current_canvas: Image.Image | None = None

    for idx, image_path in enumerate(image_paths):
        if idx % cards_per_page == 0:
            if current_canvas is not None:
                page_num = idx // cards_per_page
                out_path = os.path.join(image_folder, f"proxy_sheet_{page_num}.png")
                current_canvas.save(out_path)
                output_paths.append(out_path)
                on_log("INFO", f"Created PNG: {out_path}")

            page_num = (idx // cards_per_page) + 1
            current_canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
            on_log("INFO", f"Creating page {page_num}...")

        card_on_page = idx % cards_per_page
        row, col = divmod(card_on_page, cols)
        x, y = x_positions[col], y_positions[row]

        try:
            with Image.open(image_path) as card_img:
                scaled = card_img.resize((card_w, card_h), Image.Resampling.LANCZOS)
                mask = _create_rounded_mask((card_w, card_h), corner_r)
                current_canvas.paste(scaled, (x, y), mask=mask)  # type: ignore[union-attr]
        except Exception as e:
            on_log("ERROR", f"Could not process {os.path.basename(image_path)}: {e}")

        on_progress(idx + 1, len(image_paths), os.path.basename(image_path))

    if current_canvas is not None:
        page_num = (len(image_paths) - 1) // cards_per_page + 1
        out_path = os.path.join(image_folder, f"proxy_sheet_{page_num}.png")
        current_canvas.save(out_path)
        output_paths.append(out_path)
        on_log("INFO", f"Created PNG: {out_path}")

    return output_paths


def create_transformer_png(
    image_folder: str,
    settings: PrintSettings,
    on_log: LogCallback = _noop_log,
    on_progress: ProgressCallback = _noop_progress,
) -> list[str]:
    """Create two-sided PNG sheets for duplex printing.

    Args:
        image_folder: Path to folder containing paired card images.
        settings: Print settings.
        on_log: Logging callback.
        on_progress: Progress callback.

    Returns:
        List of paths to created PNG files (front and back alternating).
    """
    card_w = _mm_to_px(settings.card_width_mm)
    card_h = _mm_to_px(settings.card_height_mm)
    corner_r = _mm_to_px(settings.corner_radius_mm)
    padding = _mm_to_px(settings.padding_mm)

    canvas_w = int(11 * DPI)
    canvas_h = int(8.5 * DPI)

    if not os.path.isdir(image_folder):
        on_log("ERROR", f"Transformer folder does not exist: {image_folder}")
        return []

    complete_pairs = collect_transformer_pairs(image_folder)

    if not complete_pairs:
        on_log("ERROR", f"No complete image pairs found in: {image_folder}")
        return []

    on_log("INFO", f"Found {len(complete_pairs)} card pairs for two-sided PNGs.")

    x_positions, y_positions, cols, rows = _compute_grid(canvas_w, canvas_h, card_w, card_h, padding)
    cards_per_page = cols * rows
    output_paths: list[str] = []

    for i in range(0, len(complete_pairs), cards_per_page):
        sheet_pairs = complete_pairs[i : i + cards_per_page]
        sheet_num = (i // cards_per_page) + 1

        # Front faces
        canvas_front = Image.new("RGB", (canvas_w, canvas_h), "white")
        on_log("INFO", f"Creating page {sheet_num} (Front Faces)...")
        for j, pair in enumerate(sheet_pairs):
            row, col = divmod(j, cols)
            x, y = x_positions[col], y_positions[row]
            try:
                with Image.open(pair[0]) as card_img:
                    scaled = card_img.resize((card_w, card_h), Image.Resampling.LANCZOS)
                    mask = _create_rounded_mask((card_w, card_h), corner_r)
                    canvas_front.paste(scaled, (x, y), mask=mask)
            except Exception as e:
                on_log("ERROR", f"Could not process {os.path.basename(pair[0])}: {e}")

        front_path = os.path.join(image_folder, f"transformer_sheet_{sheet_num}_front.png")
        canvas_front.save(front_path)
        output_paths.append(front_path)
        on_log("INFO", f"Created front-face PNG: {front_path}")

        # Back faces (mirrored columns)
        canvas_back = Image.new("RGB", (canvas_w, canvas_h), "white")
        on_log("INFO", f"Creating page {sheet_num} (Back Faces)...")
        for j, pair in enumerate(sheet_pairs):
            row, col = divmod(j, cols)
            mirrored_col = (cols - 1) - col
            x, y = x_positions[mirrored_col], y_positions[row]
            try:
                with Image.open(pair[1]) as card_img:
                    scaled = card_img.resize((card_w, card_h), Image.Resampling.LANCZOS)
                    mask = _create_rounded_mask((card_w, card_h), corner_r)
                    canvas_back.paste(scaled, (x, y), mask=mask)
            except Exception as e:
                on_log("ERROR", f"Could not process {os.path.basename(pair[1])}: {e}")

        back_path = os.path.join(image_folder, f"transformer_sheet_{sheet_num}_back.png")
        canvas_back.save(back_path)
        output_paths.append(back_path)
        on_log("INFO", f"Created back-face PNG: {back_path}")

        on_progress(i + len(sheet_pairs), len(complete_pairs), f"Sheet {sheet_num}")

    return output_paths
