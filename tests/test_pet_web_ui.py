from pathlib import Path


WEB_DIR = Path(__file__).resolve().parents[1] / "nanobot" / "pet" / "web"
ROOT_DIR = WEB_DIR.parents[2]


def test_pet_web_uses_dog_mascot_structure() -> None:
    html = (WEB_DIR / "index.html").read_text()

    assert 'class="pet-card"' in html
    assert 'src="./assets/spark-idle.png?v=20260514-state-v1"' in html
    assert 'class="pet-name"' in html
    assert "spark" in html


def test_pet_web_uses_pywebview_drag_api() -> None:
    script = (WEB_DIR / "pet.js").read_text()

    assert "window.pywebview.api.start_drag" in script
    assert "window.pywebview.api.drag_to" in script
    assert "window.pywebview.api.end_drag" in script


def test_pet_web_maps_statuses_to_state_assets() -> None:
    script = (WEB_DIR / "pet.js").read_text()

    assert 'const avatarAssetVersion = "20260514-state-v1"' in script
    assert '"idle": versionedAsset("./assets/spark-idle.png")' in script
    assert '"working": versionedAsset("./assets/spark-working.png")' in script
    assert '"warning": versionedAsset("./assets/spark-warning.png")' in script
    assert '"dragging": versionedAsset("./assets/spark-dragging.png")' in script
    assert 'fallbackAvatarSrc = versionedAsset("./assets/spark-idle.png")' in script


def test_pet_web_truncates_bubble_text_to_50_chars() -> None:
    script = (WEB_DIR / "pet.js").read_text()

    assert "const bubbleMaxChars = 50" in script
    assert "Array.from" in script
    assert "slice(0, bubbleMaxChars)" in script
    assert "}…`;" in script


def test_pet_web_reserves_bubble_space_above_smaller_pet() -> None:
    style = (WEB_DIR / "style.css").read_text()
    commands = (ROOT_DIR / "nanobot" / "cli" / "commands.py").read_text()

    assert "width=240" in commands
    assert "height=260" in commands
    assert "width: min(240px, 100vw);" in style
    assert "min-height: 260px;" in style
    assert "grid-template-rows: 84px 1fr;" in style
    assert "width: 112px;" in style
    assert "height: 112px;" in style
