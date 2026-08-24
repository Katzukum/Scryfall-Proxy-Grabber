"""PDF renderer — arranges card images into a grid layout on PDF pages using reportlab."""

import os
from typing import Callable

from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas

from src.models import PrintSettings
from src.transformer_files import collect_transformer_pairs, get_transformer_image_paths


LogCallback = Callable[[str, str], None]
ProgressCallback = Callable[[int, int, str], None]


def _noop_log(level: str, message: str) -> None:
    pass


def _noop_progress(current: int, total: int, label: str) -> None:
    pass


def _draw_cutting_grid(
    c: canvas.Canvas,
    page_w: float,
    page_h: float,
    x_positions: list[float],
    y_positions: list[float],
    card_w: float,
    card_h: float,
) -> None:
    """Draw a precise cutting grid on the canvas."""
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.5)
    for x in x_positions:
        c.line(x, 0, x, page_h)
        c.line(x + card_w, 0, x + card_w, page_h)
    for y in y_positions:
        c.line(0, y, page_w, y)
        c.line(0, y + card_h, page_w, y + card_h)


def _get_image_paths(folder: str) -> list[str]:
    """Collect and sort all image files from a folder."""
    return get_transformer_image_paths(folder)


def _compute_grid(
    page_w: float, page_h: float, card_w: float, card_h: float, padding: float
) -> tuple[list[float], list[float], int, int]:
    """Compute card grid positions centered on the page.

    Returns:
        (x_positions, y_positions, cols, rows)
    """
    cols = 4
    rows = 2
    grid_w = (cols * card_w) + ((cols - 1) * padding)
    grid_h = (rows * card_h) + ((rows - 1) * padding)
    margin_x = (page_w - grid_w) / 2
    margin_y = (page_h - grid_h) / 2
    x_positions = [margin_x + i * (card_w + padding) for i in range(cols)]
    y_positions = [margin_y + i * (card_h + padding) for i in range(rows)]
    y_positions.reverse()
    return x_positions, y_positions, cols, rows


def create_proxy_pdf(
    image_folder: str,
    settings: PrintSettings,
    on_log: LogCallback = _noop_log,
    on_progress: ProgressCallback = _noop_progress,
) -> str | None:
    """Create a single-sided proxy PDF from images in the folder.

    Args:
        image_folder: Path to folder containing card images.
        settings: Print settings (dimensions, padding, etc.).
        on_log: Logging callback.
        on_progress: Progress callback.

    Returns:
        Path to the created PDF, or None on failure.
    """
    card_w = settings.card_width_mm * mm
    card_h = settings.card_height_mm * mm
    corner_r = settings.corner_radius_mm * mm
    padding = settings.padding_mm * mm
    page_w, page_h = landscape(letter)

    if not os.path.isdir(image_folder):
        on_log("ERROR", f"Folder does not exist: {image_folder}")
        return None

    image_paths = _get_image_paths(image_folder)
    if not image_paths:
        on_log("ERROR", f"No images found in: {image_folder}")
        return None

    on_log("INFO", f"Found {len(image_paths)} images for single-sided PDF.")
    output_path = os.path.join(image_folder, "__proxies.pdf")
    c = canvas.Canvas(output_path, pagesize=landscape(letter))
    x_positions, y_positions, cols, rows = _compute_grid(page_w, page_h, card_w, card_h, padding)
    cards_per_page = cols * rows

    for idx, image_path in enumerate(image_paths):
        if idx % cards_per_page == 0:
            if idx > 0:
                c.showPage()
            page_num = (idx // cards_per_page) + 1
            on_log("INFO", f"Creating page {page_num}...")
            _draw_cutting_grid(c, page_w, page_h, x_positions, y_positions, card_w, card_h)

        card_on_page = idx % cards_per_page
        row, col = divmod(card_on_page, cols)
        x, y = x_positions[col], y_positions[row]

        try:
            c.saveState()
            path = c.beginPath()
            path.roundRect(x, y, card_w, card_h, corner_r)
            c.clipPath(path, stroke=0, fill=0)
            c.drawImage(image_path, x, y, width=card_w, height=card_h, preserveAspectRatio=True)
            c.restoreState()
        except Exception as e:
            on_log("ERROR", f"Could not process {os.path.basename(image_path)}: {e}")

        on_progress(idx + 1, len(image_paths), os.path.basename(image_path))

    c.save()
    on_log("INFO", f"Created single-sided PDF: {output_path}")
    return output_path


def create_transformer_pdf(
    image_folder: str,
    settings: PrintSettings,
    on_log: LogCallback = _noop_log,
    on_progress: ProgressCallback = _noop_progress,
) -> str | None:
    """Create a two-sided transformer PDF for duplex printing.

    Args:
        image_folder: Path to folder containing paired card images.
        settings: Print settings.
        on_log: Logging callback.
        on_progress: Progress callback.

    Returns:
        Path to the created PDF, or None on failure.
    """
    card_w = settings.card_width_mm * mm
    card_h = settings.card_height_mm * mm
    corner_r = settings.corner_radius_mm * mm
    padding = settings.padding_mm * mm
    page_w, page_h = landscape(letter)

    if not os.path.isdir(image_folder):
        on_log("ERROR", f"Transformer folder does not exist: {image_folder}")
        return None

    complete_pairs = collect_transformer_pairs(image_folder)

    if not complete_pairs:
        on_log("ERROR", f"No complete image pairs found in: {image_folder}")
        return None

    on_log("INFO", f"Found {len(complete_pairs)} card pairs for two-sided PDF.")
    output_path = os.path.join(image_folder, "__transformers_2-sided.pdf")
    c = canvas.Canvas(output_path, pagesize=landscape(letter))
    x_positions, y_positions, cols, rows = _compute_grid(page_w, page_h, card_w, card_h, padding)
    cards_per_page = cols * rows

    for i in range(0, len(complete_pairs), cards_per_page):
        sheet_pairs = complete_pairs[i : i + cards_per_page]
        pdf_page_num = (i // cards_per_page) * 2 + 1

        # Front faces
        on_log("INFO", f"Creating page {pdf_page_num} (Front Faces)...")
        _draw_cutting_grid(c, page_w, page_h, x_positions, y_positions, card_w, card_h)
        for j, pair in enumerate(sheet_pairs):
            row, col = divmod(j, cols)
            x, y = x_positions[col], y_positions[row]
            try:
                c.saveState()
                path = c.beginPath()
                path.roundRect(x, y, card_w, card_h, corner_r)
                c.clipPath(path, stroke=0, fill=0)
                c.drawImage(pair[0], x, y, width=card_w, height=card_h, preserveAspectRatio=True)
                c.restoreState()
            except Exception as e:
                on_log("ERROR", f"Could not process {os.path.basename(pair[0])}: {e}")
        c.showPage()

        # Back faces (mirrored columns for duplex alignment)
        on_log("INFO", f"Creating page {pdf_page_num + 1} (Back Faces)...")
        _draw_cutting_grid(c, page_w, page_h, x_positions, y_positions, card_w, card_h)
        for j, pair in enumerate(sheet_pairs):
            row, col = divmod(j, cols)
            mirrored_col = (cols - 1) - col
            x, y = x_positions[mirrored_col], y_positions[row]
            try:
                c.saveState()
                path = c.beginPath()
                path.roundRect(x, y, card_w, card_h, corner_r)
                c.clipPath(path, stroke=0, fill=0)
                c.drawImage(pair[1], x, y, width=card_w, height=card_h, preserveAspectRatio=True)
                c.restoreState()
            except Exception as e:
                on_log("ERROR", f"Could not process {os.path.basename(pair[1])}: {e}")

        if i + cards_per_page < len(complete_pairs):
            c.showPage()

        on_progress(i + len(sheet_pairs), len(complete_pairs), f"Sheet {pdf_page_num // 2 + 1}")

    c.save()
    on_log("INFO", f"Created two-sided PDF: {output_path}")
    return output_path
