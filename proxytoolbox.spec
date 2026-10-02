from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_root = Path.cwd()
sys.path.insert(0, str(project_root))
from src.deck_theme.assets import ARCHIVE_FILES, RUNTIME_LICENSES

theme_staging = project_root / "assets" / "deck-theme-runtimes"
datas = [
    (str(project_root / "frontend" / "dist"), "frontend/dist"),
    (str(project_root / "assets" / "proxytoolbox-icon.ico"), "assets"),
]
# Bundle only pinned runtime files and licenses. Never collect model weights,
# download caches, benchmarks, or unrelated files from the staging directories.
for group in ("editor", "enhancer"):
    runtime_files = tuple(asset for _, asset in ARCHIVE_FILES[group]) + (RUNTIME_LICENSES[group],)
    for asset in runtime_files:
        source = theme_staging / asset.path
        if not source.is_file():
            raise RuntimeError("Run scripts/prepare_deck_theme_runtimes.py before packaging ProxyToolBox.")
        datas.append((str(source), str(Path("deck-theme-runtimes") / Path(asset.path).parent)))

# Ensure pywebview backends and package resources are bundled for Windows.
datas += collect_data_files("webview")
hiddenimports = collect_submodules("webview")
hiddenimports += ["_cffi_backend"]


a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ProxyToolBox",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / "assets" / "proxytoolbox-icon.ico"),
)
