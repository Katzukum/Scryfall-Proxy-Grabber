import os
import sys
import ctypes
from pathlib import Path

import webview

from src.api import Api
from src.app_version import APP_VERSION


def _resource_root() -> Path:
    """Return the directory containing bundled runtime resources."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def _launch_root() -> Path:
    """Return the folder the user launched the app from."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _set_windows_app_id() -> None:
    """Give the process a stable Windows app identity for taskbar grouping."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ProxyToolBox.v2")
    except Exception:
        pass


def _set_native_window_icon(window: webview.Window, icon_path: str) -> None:
    """Apply a custom Windows icon after the native form exists."""
    try:
        if not window.native or not os.path.exists(icon_path):
            return

        from System import Action
        from System.Drawing import Icon

        def _apply() -> None:
            window.native.Icon = Icon(icon_path)

        window.native.Invoke(Action(_apply))
    except Exception:
        # Fallback silently on non-Windows backends or if pythonnet interop differs.
        pass


def main() -> None:
    """Launch the ProxyToolBox desktop application."""
    _set_windows_app_id()
    api = Api()

    dev_mode = "--dev" in sys.argv

    resource_root = _resource_root()
    launch_root = _launch_root()
    os.chdir(launch_root)

    icon_path = resource_root / "assets" / "proxytoolbox-icon.ico"

    if dev_mode:
        url = "http://localhost:5173"
    else:
        # Resolve built frontend assets from the bundled resource directory.
        dist_path = resource_root / "frontend" / "dist" / "index.html"
        if not dist_path.exists():
            print(f"ERROR: Built frontend not found at {dist_path}")
            print("Run 'cd frontend && npm run build' first, or use '--dev' for development mode.")
            sys.exit(1)
        url = str(dist_path)

    window = webview.create_window(
        title=f"ProxyToolBox v{APP_VERSION}",
        url=url,
        js_api=api,
        width=950,
        height=750,
        min_size=(800, 600),
    )

    window.events.shown += lambda: _set_native_window_icon(window, str(icon_path))
    api.set_window(window)
    webview.start(debug=dev_mode)


if __name__ == "__main__":
    main()
