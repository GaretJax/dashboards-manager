import os
import shutil
import signal
import subprocess
from pathlib import Path

HIDE_CURSOR_KEY = "F8"
_MANAGED_START = "<!-- kiosk-agent-cursor:start -->"
_MANAGED_END = "<!-- kiosk-agent-cursor:end -->"
_LEGACY_START = "<!-- kiosk-agent-pre-render:start -->"
_LEGACY_END = "<!-- kiosk-agent-pre-render:end -->"


class WaylandSetupError(RuntimeError):
    """Raised when labwc cursor setup is unavailable."""


def default_labwc_config_path() -> Path:
    return Path.home() / ".config" / "labwc" / "rc.xml"


def render_labwc_keybindings() -> str:
    return f"""{_MANAGED_START}
    <keybind key="W-A-{HIDE_CURSOR_KEY}">
      <action name="HideCursor" />
    </keybind>
{_MANAGED_END}"""


def install_labwc_keybindings(path: Path | None = None) -> Path:
    config_path = path or default_labwc_config_path()
    block = render_labwc_keybindings()
    try:
        current = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        current = ""

    if _LEGACY_START in current or _LEGACY_END in current:
        if (
            current.count(_LEGACY_START) != 1
            or current.count(_LEGACY_END) != 1
        ):
            raise WaylandSetupError(
                f"invalid legacy managed block markers in {config_path}"
            )
        before, remainder = current.split(_LEGACY_START, 1)
        _, after = remainder.split(_LEGACY_END, 1)
        current = before + after

    if _MANAGED_START in current or _MANAGED_END in current:
        if (
            current.count(_MANAGED_START) != 1
            or current.count(_MANAGED_END) != 1
        ):
            raise WaylandSetupError(
                f"invalid managed block markers in {config_path}"
            )
        before, remainder = current.split(_MANAGED_START, 1)
        _, after = remainder.split(_MANAGED_END, 1)
        updated = before + block + after
    elif not current.strip():
        updated = (
            '<?xml version="1.0"?>\n'
            "<labwc_config>\n"
            "  <keyboard>\n"
            f"    {block}\n"
            "  </keyboard>\n"
            "</labwc_config>\n"
        )
    elif "</keyboard>" in current:
        updated = current.replace(
            "</keyboard>", f"  {block}\n  </keyboard>", 1
        )
    elif "</labwc_config>" in current:
        keyboard = f"  <keyboard>\n    {block}\n  </keyboard>\n"
        updated = current.replace(
            "</labwc_config>", keyboard + "</labwc_config>", 1
        )
    else:
        raise WaylandSetupError(
            f"cannot find labwc_config root in {config_path}"
        )

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(updated, encoding="utf-8")
    return config_path


def _tool(name: str) -> str:
    executable = shutil.which(name)
    if executable:
        return executable
    raise WaylandSetupError(
        f"missing Wayland tool: {name}; install with `sudo apt install {name}`"
    )


def hide_cursor():
    _press_key(HIDE_CURSOR_KEY)


def _press_key(key: str):
    try:
        subprocess.run(  # noqa: S603
            [
                _tool("wtype"),
                "-M",
                "logo",
                "-M",
                "alt",
                "-k",
                key,
                "-m",
                "alt",
                "-m",
                "logo",
            ],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise WaylandSetupError(
            f"could not invoke labwc cursor action {key}: {exc}"
        ) from exc


def require_wayland_tools():
    for name in ("labwc", "wtype"):
        _tool(name)


def _labwc_pid(proc_root: Path = Path("/proc")) -> int:
    configured_pid = os.environ.get("LABWC_PID")
    if configured_pid:
        try:
            candidates = [int(configured_pid)]
        except ValueError as exc:
            raise WaylandSetupError("LABWC_PID is not a valid PID") from exc
    else:
        candidates = []
        for process in proc_root.iterdir():
            if not process.name.isdigit():
                continue
            try:
                candidates.append(int(process.name))
            except ValueError:
                continue

    valid = []
    for pid in candidates:
        process = proc_root / str(pid)
        try:
            owned = process.stat().st_uid == os.getuid()
            is_labwc = (process / "comm").read_text(
                encoding="utf-8"
            ).strip() == "labwc"
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if owned and is_labwc:
            valid.append(pid)

    if len(valid) != 1:
        detail = "none found" if not valid else "multiple found"
        raise WaylandSetupError(
            f"could not select current user's labwc process ({detail}); "
            "set LABWC_PID or use --no-reconfigure"
        )
    return valid[0]


def reconfigure_labwc():
    pid = _labwc_pid()
    try:
        os.kill(pid, signal.SIGHUP)
    except (OSError, ProcessLookupError) as exc:
        raise WaylandSetupError(f"could not reconfigure labwc: {exc}") from exc
