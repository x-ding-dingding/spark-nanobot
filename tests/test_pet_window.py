from nanobot.pet.window import (
    ALL_SPACES_COLLECTION_BEHAVIOR,
    PetWindowApi,
    apply_all_spaces_behavior,
)


class FakeWindow:
    def __init__(self) -> None:
        self.x = 100
        self.y = 80
        self.moves: list[tuple[int, int]] = []

    def move(self, x: int, y: int) -> None:
        self.x = x
        self.y = y
        self.moves.append((x, y))


class FakeNativeWindow:
    def __init__(self, initial_behavior: int = 4) -> None:
        self._behavior = initial_behavior
        self.applied: int | None = None
        self.can_hide: bool | None = None
        self.level: int | None = None

    def collectionBehavior(self) -> int:
        return self._behavior

    def setCollectionBehavior_(self, behavior: int) -> None:
        self.applied = behavior

    def setCanHide_(self, can_hide: bool) -> None:
        self.can_hide = can_hide

    def setLevel_(self, level: int) -> None:
        self.level = level


class FakeShownEvent:
    def __init__(self, window: "FakePyWebviewWindow", native: FakeNativeWindow) -> None:
        self.window = window
        self.native = native
        self.waited_with: float | None = None

    def wait(self, timeout: float) -> bool:
        self.waited_with = timeout
        self.window.native = self.native
        return True


class FakeEvents:
    def __init__(self, shown: FakeShownEvent) -> None:
        self.shown = shown


class FakePyWebviewWindow:
    def __init__(self, native_after_show: FakeNativeWindow) -> None:
        self.native = None
        shown = FakeShownEvent(self, native_after_show)
        self.events = FakeEvents(shown)
        self.shown = shown


def test_pet_window_api_drags_on_both_axes() -> None:
    window = FakeWindow()
    api = PetWindowApi()
    api.attach(window)

    assert api.start_drag(300, 400) is True
    assert api.drag_to(325, 445) is True

    assert window.moves == [(125, 125)]


def test_pet_window_api_ignores_drag_before_start() -> None:
    window = FakeWindow()
    api = PetWindowApi()
    api.attach(window)

    assert api.drag_to(325, 445) is False
    assert window.moves == []


def test_apply_all_spaces_behavior_preserves_existing_flags() -> None:
    native = FakeNativeWindow(initial_behavior=4)

    assert apply_all_spaces_behavior(native) is True
    assert native.applied == 4 | ALL_SPACES_COLLECTION_BEHAVIOR


def test_keep_window_visible_waits_until_pywebview_window_is_shown() -> None:
    from nanobot.pet.window import keep_window_visible_on_all_spaces

    native = FakeNativeWindow(initial_behavior=4)
    window = FakePyWebviewWindow(native_after_show=native)

    assert keep_window_visible_on_all_spaces(window, schedule_on_main_thread=False) is True
    assert window.shown.waited_with == 10
    assert native.applied == 4 | ALL_SPACES_COLLECTION_BEHAVIOR
    assert native.can_hide is False
