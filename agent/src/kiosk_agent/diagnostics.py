import getpass
import shutil
import subprocess
from pathlib import Path

import httpx
from attrs import define

from .api import ManagerClient, ManagerError
from .browser import BrowserError, find_browser
from .cec import CecError, detect_cec_ports, list_cec_ports
from .display import display_environment_detail, display_environment_ready
from .paths import ephemeral_runtime_reason, get_paths
from .service import unit_path


@define(frozen=True, slots=True)
class CheckResult:
    name: str
    level: str
    detail: str


def _result(name: str, ok: bool, detail: str) -> CheckResult:
    return CheckResult(name, "ok" if ok else "fail", detail)


def _warning(name: str, detail: str) -> CheckResult:
    return CheckResult(name, "warn", detail)


def _writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True


def _systemd_user_check() -> CheckResult:
    systemctl = shutil.which("systemctl")
    if systemctl is None:
        return _result("systemd", False, "systemctl not found")
    result = subprocess.run(  # noqa: S603
        [systemctl, "--user", "is-system-running"],
        capture_output=True,
        text=True,
        check=False,
    )
    detail = (result.stdout or result.stderr).strip() or "unknown state"
    if detail == "running":
        return _result("systemd user manager", True, detail)
    if detail == "degraded":
        return _warning("systemd user manager", detail)
    return _result("systemd user manager", False, detail)


def _graphical_session_check() -> CheckResult:
    systemctl = shutil.which("systemctl")
    if systemctl is None:
        return _warning("graphical session", "systemd unavailable")
    result = subprocess.run(  # noqa: S603
        [systemctl, "--user", "is-active", "graphical-session.target"],
        capture_output=True,
        text=True,
        check=False,
    )
    detail = (result.stdout or result.stderr).strip() or "inactive"
    if result.returncode == 0:
        return _result("graphical session", True, detail)
    if display_environment_ready():
        return _warning(
            "graphical session",
            f"{detail}; display environment detected: "
            f"{display_environment_detail()}",
        )
    return _result("graphical session", False, detail)


def _linger_check() -> CheckResult:
    if shutil.which("loginctl") is None:
        return _warning("user linger", "loginctl unavailable")
    user = getpass.getuser()
    loginctl = shutil.which("loginctl")
    if loginctl is None:
        return _warning("user linger", "loginctl unavailable")
    result = subprocess.run(  # noqa: S603
        [loginctl, "show-user", user, "-p", "Linger", "--value"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return _warning("user linger", "could not determine state")
    state = result.stdout.strip().lower()
    return _warning(
        "user linger",
        "enabled"
        if state == "yes"
        else "disabled; okay with graphical autologin",
    )


def _cec_check(cec_port: str | None) -> CheckResult:
    try:
        ports = list_cec_ports() if cec_port else detect_cec_ports()
    except CecError as exc:
        if cec_port is None:
            return _warning("HDMI-CEC", f"skipped; {exc}")
        return _result("HDMI-CEC", False, str(exc))

    if cec_port:
        if cec_port in ports or Path(cec_port).exists():
            return _result(
                "HDMI-CEC",
                True,
                f"configured {cec_port}; detected {', '.join(ports) or 'none'}",
            )
        return _result(
            "HDMI-CEC",
            False,
            f"configured {cec_port}; detected {', '.join(ports) or 'none'}",
        )
    if ports:
        return _warning(
            "HDMI-CEC",
            f"detected {', '.join(ports)}; pass --cec-port to enable power control",
        )
    return _warning("HDMI-CEC", "no CEC ports detected")


def _cdp_check(cdp_url: str) -> CheckResult:
    try:
        response = httpx.get(f"{cdp_url.rstrip('/')}/json/version", timeout=2)
        response.raise_for_status()
        version = response.json().get("Browser", "unknown browser")
    except (httpx.HTTPError, ValueError) as exc:
        return _result("Chrome CDP", False, str(exc))
    return _result("Chrome CDP", True, str(version))


def run_checks(
    *,
    manager_url: str | None = None,
    screen_token: str | None = None,
    cdp_url: str = "http://127.0.0.1:9222",
    browser: str | None = None,
    cec_port: str | None = None,
    require_persistent: bool = False,
    include_service: bool = True,
) -> list[CheckResult]:
    results = []
    runtime_reason = ephemeral_runtime_reason()
    if runtime_reason:
        level = "fail" if require_persistent else "warn"
        results.append(
            CheckResult(
                "persistent installation",
                level,
                f"{runtime_reason}; uvx is unsuitable for services",
            )
        )
    else:
        results.append(
            _result("persistent installation", True, "stable interpreter path")
        )

    paths = get_paths()
    results.append(
        _result(
            "agent data directory",
            _writable_directory(paths.data),
            str(paths.data),
        )
    )
    results.append(
        _result(
            "agent config directory",
            _writable_directory(paths.config),
            str(paths.config),
        )
    )

    try:
        browser_path = find_browser(browser)
    except BrowserError as exc:
        results.append(_result("Chromium", False, str(exc)))
    else:
        results.append(_result("Chromium", True, browser_path))

    results.append(
        _result(
            "graphical display",
            display_environment_ready(),
            display_environment_detail(),
        )
    )

    if include_service:
        results.extend(
            [
                _systemd_user_check(),
                _graphical_session_check(),
                _linger_check(),
            ]
        )

    results.append(_cec_check(cec_port))
    results.append(_cdp_check(cdp_url))

    if manager_url and screen_token:
        client = ManagerClient(manager_url, screen_token)
        try:
            config = client.fetch_config()
        except ManagerError as exc:
            results.append(_result("manager API", False, str(exc)))
        else:
            results.append(
                _result(
                    "manager API",
                    True,
                    f"version {config.version}, {len(config.items)} URLs",
                )
            )
        finally:
            client.close()
    else:
        results.append(
            _warning(
                "manager API", "skipped; manager and screen token required"
            )
        )

    return results


def service_unit_check(
    scope: str, config_name: str | None = None
) -> CheckResult:
    path = unit_path(scope, config_name)
    return _result("service unit", path.exists(), str(path))
