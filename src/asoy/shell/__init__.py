"""Desktop Shell: pywebview window, job queue, progress, review UI (ARCHITECTURE section 4.1).

The shell owns the window. `__main__` parses arguments and calls in here; it never touches
pywebview itself. Frontend assets are resolved through importlib.resources so that an installed
wheel behaves the same as a source checkout (ADR-018).
"""

from __future__ import annotations

import sys
from importlib.resources import as_file, files

WINDOW_TITLE = "Asoy"
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 640

WEBVIEW2_MISSING = (
    "Asoy could not start the WebView2 runtime, which it uses to render its interface.\n"
    "\n"
    "Install the Microsoft Edge WebView2 Runtime (the evergreen bootstrapper) from:\n"
    "  https://developer.microsoft.com/microsoft-edge/webview2/\n"
    "\n"
    "It is preinstalled on Windows 11 and current Windows 10, so this usually means an\n"
    "older build. Install it, then run Asoy again."
)


class ShellApi:
    """Methods exposed to the frontend over the pywebview JS bridge."""

    def __init__(self, version: str) -> None:
        self._version = version

    def get_version(self) -> str:
        """Return the installed version. The frontend calls this to prove the bridge works."""
        return self._version

    def get_tier(self) -> dict[str, object]:
        """Return the detected hardware tier. Invariant 8: the active tier is always visible."""
        from asoy.tiers import detect

        result = detect()
        return {
            "tier": result.tier.value,
            "device": result.device_name,
            "vram_gib": result.total_vram_gib,
            "reason": result.reason,
        }


def run_window(version: str) -> int:
    """Open the shell window and block until it closes. Returns a process exit code."""
    import webview
    from webview.errors import WebViewException

    with as_file(files("asoy.shell") / "web") as web_dir:
        index = web_dir / "index.html"
        if not index.is_file():
            print(
                f"Frontend assets are missing from the installation: {index}\n"
                "Reinstall Asoy, or run 'uv sync' if you are working from a source checkout.",
                file=sys.stderr,
            )
            return 1

        try:
            webview.create_window(
                WINDOW_TITLE,
                url=index.as_uri(),
                js_api=ShellApi(version),
                width=WINDOW_WIDTH,
                height=WINDOW_HEIGHT,
                resizable=True,
            )
            webview.start()
        except WebViewException as exc:
            print(f"{WEBVIEW2_MISSING}\n\nUnderlying error: {exc}", file=sys.stderr)
            return 1

    return 0
