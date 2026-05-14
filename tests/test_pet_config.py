from nanobot.config.loader import convert_keys
from nanobot.config.schema import Config


def test_desktop_pet_config_defaults() -> None:
    config = Config()

    assert config.desktop_pet.enabled is False
    assert config.desktop_pet.host == "127.0.0.1"
    assert config.desktop_pet.port == 18791
    assert config.desktop_pet.show_mode == "high_signal"
    assert config.desktop_pet.bubble_max_chars == 160
    assert config.desktop_pet.auto_launch is False


def test_desktop_pet_config_loads_from_camel_case() -> None:
    raw = {
        "desktopPet": {
            "enabled": True,
            "host": "0.0.0.0",
            "port": 19000,
            "showMode": "all",
            "bubbleMaxChars": 80,
            "autoLaunch": True,
        }
    }

    config = Config.model_validate(convert_keys(raw))

    assert config.desktop_pet.enabled is True
    assert config.desktop_pet.host == "0.0.0.0"
    assert config.desktop_pet.port == 19000
    assert config.desktop_pet.show_mode == "all"
    assert config.desktop_pet.bubble_max_chars == 80
    assert config.desktop_pet.auto_launch is True
