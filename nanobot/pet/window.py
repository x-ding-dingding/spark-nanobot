"""Native window helpers for the desktop pet."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# NSWindowCollectionBehaviorCanJoinAllSpaces | Stationary | FullScreenAuxiliary.
ALL_SPACES_COLLECTION_BEHAVIOR = (1 << 0) | (1 << 4) | (1 << 8)


def apply_all_spaces_behavior(native_window: Any) -> bool:
    """Make a native macOS window visible across Spaces while preserving flags."""
    try:
        current = int(native_window.collectionBehavior())
        native_window.setCollectionBehavior_(current | ALL_SPACES_COLLECTION_BEHAVIOR)
        return True
    except Exception:
        return False


def _apply_pet_window_behavior(native_window: Any) -> bool:
    """Apply native window settings that make the pet behave like a desktop overlay."""
    applied = apply_all_spaces_behavior(native_window)

    try:
        native_window.setCanHide_(False)
    except Exception:
        pass

    try:
        import AppKit  # type: ignore[import-not-found]

        native_window.setLevel_(AppKit.NSStatusWindowLevel)
    except Exception:
        pass

    return applied


def _resolve_native_window(window: Any, wait_timeout: float) -> Any | None:
    """Wait for pywebview to create the Cocoa window before reading ``native``."""
    native_window = getattr(window, "native", None)
    if native_window is not None:
        return native_window

    events = getattr(window, "events", None)
    shown = getattr(events, "shown", None)
    wait = getattr(shown, "wait", None)
    if callable(wait):
        try:
            if not wait(wait_timeout):
                return None
        except Exception:
            return None

    return getattr(window, "native", None)


def keep_window_visible_on_all_spaces(
    window: Any,
    *,
    wait_timeout: float = 10,
    schedule_on_main_thread: bool = True,
) -> bool:
    """Best-effort pywebview hook for macOS all-Spaces pet behavior."""
    native_window = _resolve_native_window(window, wait_timeout)
    if native_window is None:
        return False

    if not schedule_on_main_thread:
        return _apply_pet_window_behavior(native_window)

    try:
        from PyObjCTools import AppHelper  # type: ignore[import-not-found]

        AppHelper.callAfter(_apply_pet_window_behavior, native_window)
        return True
    except Exception:
        return _apply_pet_window_behavior(native_window)


@dataclass
class _DragState:
    screen_x: float
    screen_y: float
    window_x: int
    window_y: int


class PetWindowApi:
    """Small JS bridge used by the WebView pet to drag a frameless window."""

    def __init__(self) -> None:
        self._window: Any | None = None
        self._drag: _DragState | None = None

    def attach(self, window: Any) -> None:
        self._window = window

    def start_drag(self, screen_x: float, screen_y: float) -> bool:
        if self._window is None:
            return False

        try:
            self._drag = _DragState(
                screen_x=float(screen_x),
                screen_y=float(screen_y),
                window_x=int(self._window.x),
                window_y=int(self._window.y),
            )
            return True
        except Exception:
            self._drag = None
            return False

    def drag_to(self, screen_x: float, screen_y: float) -> bool:
        if self._window is None or self._drag is None:
            return False

        try:
            dx = float(screen_x) - self._drag.screen_x
            dy = float(screen_y) - self._drag.screen_y
            self._window.move(
                round(self._drag.window_x + dx),
                round(self._drag.window_y + dy),
            )
            return True
        except Exception:
            return False

    def end_drag(self) -> bool:
        self._drag = None
        return True
