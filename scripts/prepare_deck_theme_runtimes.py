"""Stage verified internal inference binaries for PyInstaller; never downloads models."""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.deck_theme.assets import AssetManager  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "assets" / "deck-theme-runtimes")
    parser.add_argument("--include-cuda", action="store_true", help="Also stage the optional NVIDIA editor runtime")
    args = parser.parse_args()
    manager = AssetManager(args.output)
    for group in ("editor", "enhancer"):
        print(f"Preparing {group} runtime...")
        manager.install_runtime(group, threading.Event(), lambda done, total, message: None)
    if args.include_cuda:
        print("Preparing optional NVIDIA editor runtime...")
        manager.install_editor_cuda_runtime(threading.Event(), lambda done, total, message: None)
    print(f"Verified runtimes staged in {args.output / 'runtimes'}")


if __name__ == "__main__":
    main()
