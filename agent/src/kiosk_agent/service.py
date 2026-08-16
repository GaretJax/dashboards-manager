import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .config import config_path, validate_config_name
from .display import runtime_directory
from .paths import APP_NAME, ephemeral_runtime_reason

SERVICE_TEMPLATE_NAME = "kiosk-agent@.service"


def service_instance_name(config_ref: str | Path) -> str:
    config_name = config_path(config_ref).stem
    validate_config_name(config_name)
    return f"kiosk-agent@{config_name}.service"


def _user_unit_directory() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def installed_service_instances(scope: str) -> list[str]:
    if scope == "user":
        directory = _user_unit_directory() / "default.target.wants"
    elif scope == "system":
        directory = Path("/etc/systemd/system/graphical.target.wants")
    else:
        raise ValueError(f"unsupported systemd scope: {scope}")
    return sorted(
        path.name
        for path in directory.glob("kiosk-agent@*.service")
        if path.name != SERVICE_TEMPLATE_NAME
    )


def unit_path(scope: str, config_name: str | Path | None = None) -> Path:
    if scope == "user":
        directory = _user_unit_directory()
    elif scope == "system":
        directory = Path("/etc/systemd/system")
    else:
        raise ValueError(f"unsupported systemd scope: {scope}")
    name = (
        service_instance_name(config_name)
        if config_name is not None
        else SERVICE_TEMPLATE_NAME
    )
    return directory / name


def _systemctl_command(scope: str, *arguments: str) -> list[str]:
    command = ["systemctl"]
    if scope == "user":
        command.append("--user")
    command.extend(arguments)
    return command


def run_systemctl(scope: str, *arguments: str, check: bool = True):
    if shutil.which("systemctl") is None:
        raise RuntimeError("systemctl is not installed")
    result = subprocess.run(  # noqa: S603
        _systemctl_command(scope, *arguments), check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"systemctl command failed with status {result.returncode}"
        )
    return result


def run_journalctl(
    scope: str,
    follow: bool = False,
    lines: int = 100,
    config_name: str | Path | None = None,
):
    if shutil.which("journalctl") is None:
        raise RuntimeError("journalctl is not installed")
    service_name = (
        service_instance_name(config_name)
        if config_name is not None
        else SERVICE_TEMPLATE_NAME
    )
    command = ["journalctl"]
    if scope == "user":
        service_uid = os.environ.get("SUDO_UID") or str(os.getuid())
        command.extend(
            [
                f"_SYSTEMD_USER_UNIT={service_name}",
                f"_UID={service_uid}",
            ]
        )
    else:
        command.extend(["-u", service_name])
    command.extend(["--no-pager", "-n", str(lines)])
    if follow:
        command.append("-f")
    return subprocess.run(command, check=False)  # noqa: S603


def _run_command(config_ref: str | Path | None = None) -> list[str]:
    config_argument = (
        "%i" if config_ref is None else str(config_path(config_ref))
    )
    return [
        sys.executable,
        "-m",
        "kiosk_agent",
        "run",
        "--config",
        config_argument,
    ]


def render_unit(
    *,
    scope: str,
    manager: str | None = None,
    screen: str | None = None,
    browser: str | None = None,
    cdp_url: str | None = None,
    poll_interval: float | None = None,
    profile_dir: Path | None = None,
    ephemeral_profile: bool = False,
    launch_browser: bool = True,
    log_level: str = "INFO",
    user: str | None = None,
    display: str | None = None,
    wayland_display: str | None = None,
    runtime_dir: str | None = None,
    config_ref: str | Path | None = None,
) -> str:
    del manager, screen, browser, cdp_url, poll_interval, profile_dir
    del ephemeral_profile, launch_browser, log_level
    if scope == "system" and not user:
        raise ValueError("system scope requires a user")

    if scope == "user":
        after = "graphical-session.target"
        wants = "Wants=graphical-session.target"
        part_of = "PartOf=graphical-session.target"
        wanted_by = "default.target"
    else:
        after = "graphical.target"
        wants = "Wants=graphical.target"
        part_of = None
        wanted_by = "graphical.target"

    lines = [
        "[Unit]",
        "Description=Kiosk Agent (%i)",
        f"After={after}",
        wants,
        *([part_of] if part_of else []),
        "",
        "[Service]",
        "Type=simple",
        f"ExecStart={shlex.join(_run_command(config_ref))}",
        "Restart=always",
        "RestartSec=5",
        "Environment=PYTHONUNBUFFERED=1",
    ]
    if scope == "system":
        lines.append(f"User={user}")

    environment = {
        "DISPLAY": display,
        "WAYLAND_DISPLAY": wayland_display,
        "XDG_RUNTIME_DIR": runtime_dir,
    }
    for name, value in environment.items():
        if value:
            lines.append(f"Environment={name}={shlex.quote(value)}")

    lines.extend(["", "[Install]", f"WantedBy={wanted_by}", ""])
    return "\n".join(lines)


def install_unit(
    unit: str,
    scope: str,
    enable: bool,
    start: bool,
    config_ref: str | Path,
):
    path = unit_path(scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != unit:
        path.write_text(unit, encoding="utf-8")
    instance = service_instance_name(config_ref)
    run_systemctl(scope, "daemon-reload")
    if enable:
        run_systemctl(scope, "enable", instance)
    if start:
        run_systemctl(scope, "restart", instance)
    return path


def uninstall_unit(scope: str, config_ref: str | Path | None = None):
    instance = (
        service_instance_name(config_ref)
        if config_ref is not None
        else SERVICE_TEMPLATE_NAME
    )
    run_systemctl(scope, "disable", "--now", instance, check=False)
    if config_ref is None:
        path = unit_path(scope)
        if path.exists():
            path.unlink()
    run_systemctl(scope, "daemon-reload")


def stable_install_error(allow_ephemeral: bool = False) -> str | None:
    if allow_ephemeral:
        return None
    reason = ephemeral_runtime_reason()
    if reason:
        return (
            "service installation requires persistent package installation; "
            f"{reason}. Install with `uv tool install {APP_NAME}` or pass "
            "--allow-ephemeral explicitly."
        )
    return None


def current_display_environment() -> dict[str, str | None]:
    environment = {
        "display": os.environ.get("DISPLAY"),
        "wayland_display": os.environ.get("WAYLAND_DISPLAY"),
        "runtime_dir": os.environ.get("XDG_RUNTIME_DIR"),
    }
    if environment["wayland_display"] and not environment["runtime_dir"]:
        environment["runtime_dir"] = runtime_directory(os.environ)
    return environment
