import json
from pathlib import Path


DATA_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "channel_settings.json"
)


def load_settings() -> dict:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not DATA_PATH.exists():
        DATA_PATH.write_text("{}", encoding="utf-8")
        return {}

    try:
        with DATA_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def save_settings(settings: dict) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    with DATA_PATH.open("w", encoding="utf-8") as file:
        json.dump(
            settings,
            file,
            ensure_ascii=False,
            indent=2,
        )


def get_channel_id(
    guild_id: int,
    feature: str,
) -> int | None:
    settings = load_settings()
    guild_settings = settings.get(str(guild_id), {})
    channel_id = guild_settings.get(feature)

    if channel_id is None:
        return None

    return int(channel_id)


def set_channel_id(
    guild_id: int,
    feature: str,
    channel_id: int,
) -> None:
    settings = load_settings()
    guild_key = str(guild_id)

    if guild_key not in settings:
        settings[guild_key] = {}

    settings[guild_key][feature] = channel_id
    save_settings(settings)


def remove_channel_id(
    guild_id: int,
    feature: str,
) -> bool:
    settings = load_settings()
    guild_key = str(guild_id)

    if guild_key not in settings:
        return False

    if feature not in settings[guild_key]:
        return False

    del settings[guild_key][feature]

    if not settings[guild_key]:
        del settings[guild_key]

    save_settings(settings)
    return True


def get_setting_enabled(
    guild_id: int,
    feature: str,
    default: bool = False,
) -> bool:
    settings = load_settings()
    guild_settings = settings.get(str(guild_id), {})
    value = guild_settings.get(feature, default)

    return bool(value)


def set_setting_enabled(
    guild_id: int,
    feature: str,
    enabled: bool,
) -> None:
    settings = load_settings()
    guild_key = str(guild_id)

    if guild_key not in settings:
        settings[guild_key] = {}

    settings[guild_key][feature] = enabled
    save_settings(settings)