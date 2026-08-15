import json
import re
import tomllib
from pathlib import Path

from .paths import get_paths

CONFIG_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
DEFAULT_CONFIG_NAME = "config"
DEFAULT_CDP_URL = "http://127.0.0.1:9222"


class ConfigError(ValueError):
    """Raised when an agent TOML configuration is invalid."""


def config_path(config_ref: str | Path | None = None) -> Path:
    if config_ref is None:
        return get_paths().config / f"{DEFAULT_CONFIG_NAME}.toml"
    raw = Path(config_ref).expanduser()
    if raw.is_absolute() or raw.parent != Path("."):
        return raw
    name = raw.stem if raw.suffix == ".toml" else raw.name
    validate_config_name(name)
    return get_paths().config / f"{name}.toml"


def validate_config_name(name: str):
    if not CONFIG_NAME_PATTERN.fullmatch(name):
        raise ConfigError(
            "config name must contain only letters, numbers, '.', '_' or '-'"
        )


def load_config(config_ref: str | Path) -> dict:
    path = config_path(config_ref)
    try:
        with path.open("rb") as stream:
            values = tomllib.load(stream)
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML config {path}: {exc}") from exc
    if not isinstance(values, dict):
        raise ConfigError(f"config root must be a TOML table: {path}")
    allowed = {
        "manager",
        "screen",
        "browser",
        "cdp_url",
        "profile_dir",
        "ephemeral_profile",
        "launch_browser",
        "poll_interval",
        "status_interval",
        "screenshot_interval",
        "log_level",
        "cec_port",
        "display",
        "wayland_display",
        "runtime_dir",
    }
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ConfigError(f"unknown config keys: {', '.join(unknown)}")
    return values


def merge_config(
    config_ref: str | Path | None,
    overrides: dict,
    *,
    allow_missing: bool = False,
) -> dict:
    if config_ref is None:
        values = {}
    else:
        path = config_path(config_ref)
        values = (
            {}
            if allow_missing and not path.exists()
            else load_config(config_ref)
        )
    values = {
        "browser": None,
        "cdp_url": DEFAULT_CDP_URL,
        "profile_dir": None,
        "ephemeral_profile": False,
        "launch_browser": True,
        "poll_interval": 15.0,
        "status_interval": 60.0,
        "screenshot_interval": 300.0,
        "log_level": "INFO",
        "cec_port": None,
        "display": None,
        "display_identity": None,
        "wayland_display": None,
        "runtime_dir": None,
        **values,
    }
    values.update(
        {key: value for key, value in overrides.items() if value is not None}
    )
    if not isinstance(values.get("manager"), str) or not values["manager"]:
        raise ConfigError("manager and screen are required")
    if not isinstance(values.get("screen"), str) or not values["screen"]:
        raise ConfigError("manager and screen are required")
    for key in ("ephemeral_profile", "launch_browser"):
        if not isinstance(values[key], bool):
            raise ConfigError(f"{key} must be boolean")
    try:
        poll_interval = float(values["poll_interval"])
    except (TypeError, ValueError, OverflowError) as exc:
        raise ConfigError("poll_interval must be numeric") from exc
    if poll_interval < 1:
        raise ConfigError("poll_interval must be at least 1 second")
    values["poll_interval"] = poll_interval
    for key in ("status_interval", "screenshot_interval"):
        try:
            interval = float(values[key])
        except (TypeError, ValueError, OverflowError) as exc:
            raise ConfigError(f"{key} must be numeric") from exc
        if interval < 1:
            raise ConfigError(f"{key} must be at least 1 second")
        values[key] = interval
    if values["display_identity"] is not None and not isinstance(
        values["display_identity"], str
    ):
        raise ConfigError("display_identity must be a string")
    if not isinstance(values["log_level"], str):
        raise ConfigError("log_level must be a string")
    values["log_level"] = values["log_level"].upper()
    if values["log_level"] not in {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    }:
        raise ConfigError("log_level is invalid")
    return values


def dump_config(name: str, values: dict) -> Path:
    validate_config_name(name)
    # nosemgrep: python-path-traversal
    path = get_paths().config / f"{name}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for key in sorted(values):
        value = values[key]
        if value is None:
            continue
        if isinstance(value, Path):
            value = str(value)
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, (int, float)):
            rendered = str(value)
        elif isinstance(value, str):
            rendered = json.dumps(value)
        else:
            raise ConfigError(f"unsupported config value for {key}")
        lines.append(f"{key} = {rendered}")
    content = "\n".join(lines) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        # pi-lens-ignore: python-path-traversal
        path.write_text(content, encoding="utf-8")
    return path
