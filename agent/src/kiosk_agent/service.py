import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .display import runtime_directory
from .paths import APP_NAME, ephemeral_runtime_reason

SERVICE_NAME = "kiosk-agent.service"


def _user_unit_directory() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def unit_path(scope: str) -> Path:
    if scope == "user":
        return _user_unit_directory() / SERVICE_NAME
    if scope == "system":
        return Path("/etc/systemd/system") / SERVICE_NAME
    raise ValueError(f"unsupported systemd scope: {scope}")


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


def run_journalctl(scope: str, follow: bool = False, lines: int = 100):
    if shutil.which("journalctl") is None:
        raise RuntimeError("journalctl is not installed")
    command = ["journalctl"]
    if scope == "user":
        command.append("--user")
    command.extend(["-u", SERVICE_NAME, "--no-pager", "-n", str(lines)])
    if follow:
        command.append("-f")
    return subprocess.run(command, check=False)  # noqa: S603


def _run_command(
    manager: str,
    screen: str,
    browser: str,
    cdp_url: str,
    poll_interval: float,
    profile_dir: Path | None,
    ephemeral_profile: bool,
    launch_browser: bool,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "kiosk_agent",
        "run",
        "--manager",
        manager,
        "--screen",
        screen,
        "--browser",
        browser,
        "--cdp-url",
        cdp_url,
        "--poll-interval",
        str(poll_interval),
    ]
    if profile_dir is not None:
        command.extend(["--profile-dir", str(profile_dir)])
    if ephemeral_profile:
        command.append("--ephemeral-profile")
    if not launch_browser:
        command.append("--no-launch-browser")
    return command


def render_unit(
    *,
    scope: str,
    manager: str,
    screen: str,
    browser: str,
    cdp_url: str,
    poll_interval: float,
    profile_dir: Path | None,
    ephemeral_profile: bool,
    launch_browser: bool,
    user: str | None = None,
    display: str | None = None,
    wayland_display: str | None = None,
    runtime_dir: str | None = None,
) -> str:
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
        "Description=Kiosk Agent",
        f"After={after}",
        wants,
        *([part_of] if part_of else []),
        "",
        "[Service]",
        "Type=simple",
        f"ExecStart={shlex.join(_run_command(manager, screen, browser, cdp_url, poll_interval, profile_dir, ephemeral_profile, launch_browser))}",
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


def install_unit(unit: str, scope: str, enable: bool, start: bool):
    path = unit_path(scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(unit, encoding="utf-8")
    run_systemctl(scope, "daemon-reload")
    if enable:
        run_systemctl(scope, "enable", SERVICE_NAME)
    if start:
        run_systemctl(scope, "start", SERVICE_NAME)
    return path


def uninstall_unit(scope: str):
    path = unit_path(scope)
    run_systemctl(scope, "disable", "--now", SERVICE_NAME, check=False)
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
    return {
        "display": os.environ.get("DISPLAY"),
        "wayland_display": os.environ.get("WAYLAND_DISPLAY"),
        "runtime_dir": runtime_directory(),
    }
