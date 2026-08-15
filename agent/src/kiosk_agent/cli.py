import json
import logging
import os
import tempfile
from pathlib import Path

import click

from . import __version__
from .api import ManagerClient, ManagerError
from .browser import BrowserController, BrowserError
from .cec import (
    CecController,
    CecError,
    detect_cec_ports,
    list_cec_ports,
)
from .config import ConfigError, dump_config, merge_config
from .diagnostics import run_checks, service_unit_check
from .display import detect_display_backend
from .paths import ensure_profile_dir
from .runner import AgentRestartRequested, AgentRunner
from .service import (
    current_display_environment,
    install_unit,
    render_unit,
    run_journalctl,
    run_systemctl,
    service_instance_name,
    stable_install_error,
    uninstall_unit,
)
from .wayland import (
    WaylandSetupError,
    default_labwc_config_path,
    hide_cursor,
    install_labwc_keybindings,
    reconfigure_labwc,
    render_labwc_keybindings,
    require_wayland_tools,
)

DEFAULT_CDP_URL = "http://127.0.0.1:9222"
LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class _HttpxRequestLogFilter(logging.Filter):
    def filter(self, record):
        if (
            record.name == "httpx"
            and record.levelno == logging.INFO
            and record.getMessage().startswith("HTTP Request:")
        ):
            record.levelno = logging.DEBUG
            record.levelname = "DEBUG"
            return logging.getLogger().getEffectiveLevel() <= logging.DEBUG
        return True


def _configure_logging(log_level):
    level = getattr(logging, log_level.upper())
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(_HttpxRequestLogFilter())


@click.group()
@click.version_option(version=__version__)
def main():
    """Run and manage Kiosk Agent."""


@main.command()
@click.option("--config", "config_ref", help="TOML config name or path.")
@click.option("--manager", help="Kiosk Manager base URL.")
@click.option("--screen", "screen_token", help="Screen token.")
@click.option("--browser", default=None, help="Chromium executable name/path.")
@click.option("--cdp-url", default=None)
@click.option(
    "--cec-port",
    default=None,
    help="HDMI-CEC device path, for example /dev/cec0.",
)
@click.option("--profile-dir", type=click.Path(path_type=Path))
@click.option("--ephemeral-profile/--no-ephemeral-profile", default=None)
@click.option("--launch-browser/--no-launch-browser", default=None)
@click.option(
    "--poll-interval",
    type=click.FloatRange(min=1),
    default=None,
)
@click.option(
    "--status-interval",
    type=click.FloatRange(min=1),
    default=None,
)
@click.option(
    "--screenshot-interval",
    type=click.FloatRange(min=1),
    default=None,
)
@click.option(
    "--log-level",
    type=click.Choice(LOG_LEVELS, case_sensitive=False),
    default=None,
    envvar="KIOSK_AGENT_LOG_LEVEL",
)
def run(
    config_ref,
    manager,
    screen_token,
    browser,
    cdp_url,
    cec_port,
    profile_dir,
    ephemeral_profile,
    launch_browser,
    poll_interval,
    status_interval,
    screenshot_interval,
    log_level,
):
    """Launch Chromium and run screen playlist."""
    try:
        values = merge_config(
            config_ref,
            {
                "manager": manager,
                "screen": screen_token,
                "browser": browser,
                "cdp_url": cdp_url,
                "cec_port": cec_port,
                "profile_dir": profile_dir,
                "ephemeral_profile": ephemeral_profile,
                "launch_browser": launch_browser,
                "poll_interval": poll_interval,
                "status_interval": status_interval,
                "screenshot_interval": screenshot_interval,
                "log_level": log_level,
            },
        )
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    manager = values["manager"]
    screen_token = values["screen"]
    browser = values["browser"]
    cdp_url = values["cdp_url"]
    cec_port = values["cec_port"]
    profile_dir = values["profile_dir"]
    ephemeral_profile = values["ephemeral_profile"]
    launch_browser = values["launch_browser"]
    poll_interval = values["poll_interval"]
    status_interval = values["status_interval"]
    screenshot_interval = values["screenshot_interval"]
    log_level = values["log_level"]
    if profile_dir:
        profile_dir = Path(profile_dir)
    if profile_dir and ephemeral_profile:
        raise click.ClickException(
            "--profile-dir and --ephemeral-profile are mutually exclusive"
        )

    temporary_profile = None
    if ephemeral_profile:
        temporary_profile = tempfile.TemporaryDirectory(prefix="kiosk-agent-")
        profile = Path(temporary_profile.name)
    else:
        profile = ensure_profile_dir(profile_dir)

    for environment_name, value_key in (
        ("DISPLAY", "display"),
        ("WAYLAND_DISPLAY", "wayland_display"),
        ("XDG_RUNTIME_DIR", "runtime_dir"),
    ):
        if values.get(value_key):
            os.environ[environment_name] = values[value_key]

    _configure_logging(log_level)
    if detect_display_backend() == "wayland":
        try:
            hide_cursor()
        except WaylandSetupError as exc:
            logging.getLogger("kiosk_agent").warning(
                "could not hide cursor: %s", exc
            )
    try:
        runner = AgentRunner(
            ManagerClient(manager, screen_token),
            BrowserController(
                browser,
                cdp_url,
                profile,
                launch=launch_browser,
            ),
            poll_interval,
            CecController(cec_port) if cec_port else None,
            status_interval,
            screenshot_interval,
        )
        runner.run()
    except AgentRestartRequested:
        logging.getLogger("kiosk_agent").info("agent restart requested")
    except (BrowserError, ManagerError, WaylandSetupError) as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        if temporary_profile is not None:
            temporary_profile.cleanup()


@main.command()
@click.option("--config", "config_ref", help="TOML config name or path.")
@click.option("--manager", help="Kiosk Manager base URL.")
@click.option("--screen", "screen_token", help="Screen token.")
@click.option("--browser", default=None, help="Chromium executable name/path.")
@click.option("--cdp-url", default=None)
@click.option("--cec-port", default=None, help="HDMI-CEC device path.")
def doctor(config_ref, manager, screen_token, browser, cdp_url, cec_port):
    """Check agent, browser, display, CEC, systemd, and manager readiness."""
    if config_ref:
        try:
            values = merge_config(
                config_ref,
                {
                    "manager": manager,
                    "screen": screen_token,
                    "browser": browser,
                    "cdp_url": cdp_url,
                    "cec_port": cec_port,
                },
            )
        except ConfigError as exc:
            raise click.ClickException(str(exc)) from exc
        manager = values["manager"]
        screen_token = values["screen"]
        browser = values["browser"]
        cdp_url = values["cdp_url"]
        cec_port = values["cec_port"]
    else:
        if bool(manager) != bool(screen_token):
            raise click.UsageError(
                "--manager and --screen must be used together"
            )
        cdp_url = cdp_url or DEFAULT_CDP_URL
    results = run_checks(
        manager_url=manager,
        screen_token=screen_token,
        cdp_url=cdp_url,
        browser=browser,
        cec_port=cec_port,
    )
    _print_checks(results)
    if any(result.level == "fail" for result in results):
        raise click.exceptions.Exit(1)


@main.command(name="config")
@click.option("--manager", required=True, help="Kiosk Manager base URL.")
@click.option("--screen", "screen_token", required=True, help="Screen token.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def config_command(manager, screen_token, output_format):
    """Fetch and print current screen configuration."""
    client = ManagerClient(manager, screen_token)
    try:
        config = client.fetch_config()
    except ManagerError as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        client.close()

    if output_format == "json":
        click.echo(
            json.dumps(
                {
                    "version": config.version,
                    "on_schedule": config.on_schedule,
                    "off_schedule": config.off_schedule,
                    "items": [
                        {
                            "content_id": item.content_id,
                            "url": item.url,
                            "duration_seconds": item.duration_seconds,
                            "order": item.order,
                            "preload_delay_seconds": item.preload_delay_seconds,
                            "preload_timeout_seconds": item.preload_timeout_seconds,
                            "injected_css": item.injected_css,
                            "injected_javascript_before": item.injected_javascript_before,
                            "injected_javascript_after": item.injected_javascript_after,
                        }
                        for item in config.items
                    ],
                },
                indent=2,
            )
        )
        return

    click.echo(f"Version: {config.version}")
    if config.on_schedule:
        click.echo(f"Power on: {config.on_schedule}")
    if config.off_schedule:
        click.echo(f"Power off: {config.off_schedule}")
    if not config.items:
        click.echo("Playlist is empty.")
        return
    for item in config.items:
        click.echo(f"{item.order}. {item.url} ({item.duration_seconds:g}s)")


@main.group(name="cec")
def cec():
    """Inspect and control HDMI-CEC adapters."""


@cec.command(name="list")
def cec_list():
    """List HDMI-CEC adapters reported by cec-client."""
    try:
        ports = list_cec_ports()
    except CecError as exc:
        raise click.ClickException(str(exc)) from exc
    if not ports:
        click.echo("No HDMI-CEC ports detected.")
        return
    for port in ports:
        click.echo(port)


@cec.command(name="detect")
def cec_detect():
    """Detect usable HDMI-CEC device paths."""
    try:
        ports = detect_cec_ports()
    except CecError as exc:
        raise click.ClickException(str(exc)) from exc
    if not ports:
        raise click.ClickException("No HDMI-CEC ports detected.")
    for port in ports:
        click.echo(port)


@main.group(name="wayland")
def wayland_command():
    """Configure labwc cursor hiding."""


@wayland_command.command(name="setup")
@click.option(
    "--labwc-config",
    type=click.Path(path_type=Path),
    help="labwc rc.xml path.",
)
@click.option(
    "--reconfigure/--no-reconfigure", default=True, show_default=True
)
@click.option("--dry-run", is_flag=True, help="Print configuration only.")
def wayland_setup(labwc_config, reconfigure, dry_run):
    """Install labwc HideCursor binding."""
    labwc_path = labwc_config or default_labwc_config_path()
    if dry_run:
        click.echo(f"--- {labwc_path}")
        click.echo(render_labwc_keybindings())
        return

    try:
        require_wayland_tools()
        installed_labwc_path = install_labwc_keybindings(labwc_path)
        if reconfigure:
            reconfigure_labwc()
    except WaylandSetupError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Updated {installed_labwc_path}")
    click.echo("labwc cursor setup complete.")


@main.group()
def service():
    """Manage systemd service installation and lifecycle."""


@service.command(name="install")
@click.option("--config", "config_name", default="config", show_default=True)
@click.option("--manager", help="Kiosk Manager base URL.")
@click.option("--screen", "screen_token", help="Screen token.")
@click.option("--browser", default=None)
@click.option("--cdp-url", default=None)
@click.option("--cec-port", default=None, help="HDMI-CEC device path.")
@click.option("--profile-dir", type=click.Path(path_type=Path))
@click.option("--ephemeral-profile/--no-ephemeral-profile", default=None)
@click.option("--launch-browser/--no-launch-browser", default=None)
@click.option("--poll-interval", type=click.FloatRange(min=1), default=None)
@click.option(
    "--log-level",
    type=click.Choice(LOG_LEVELS, case_sensitive=False),
    default=None,
    envvar="KIOSK_AGENT_LOG_LEVEL",
)
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
@click.option("--user", "service_user")
@click.option("--display")
@click.option("--wayland-display")
@click.option("--runtime-dir")
@click.option("--enable/--no-enable", default=True, show_default=True)
@click.option("--start/--no-start", default=True, show_default=True)
@click.option("--allow-ephemeral", is_flag=True)
@click.option("--dry-run", is_flag=True, help="Print generated unit only.")
def service_install(
    config_name,
    manager,
    screen_token,
    browser,
    cdp_url,
    cec_port,
    profile_dir,
    ephemeral_profile,
    launch_browser,
    poll_interval,
    log_level,
    scope,
    service_user,
    display,
    wayland_display,
    runtime_dir,
    enable,
    start,
    allow_ephemeral,
    dry_run,
):
    """Write TOML config and install idempotent templated service."""
    try:
        values = merge_config(
            config_name,
            {
                "manager": manager,
                "screen": screen_token,
                "browser": browser,
                "cdp_url": cdp_url,
                "cec_port": cec_port,
                "profile_dir": profile_dir,
                "ephemeral_profile": ephemeral_profile,
                "launch_browser": launch_browser,
                "poll_interval": poll_interval,
                "log_level": log_level,
                "display": display,
                "wayland_display": wayland_display,
                "runtime_dir": runtime_dir,
            },
            allow_missing=True,
        )
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc
    if not dry_run:
        _require_stable_install(
            bool(values["ephemeral_profile"]) and allow_ephemeral
        )
    if not dry_run and scope == "system" and os.geteuid() != 0:
        raise click.ClickException("system scope requires root")
    if scope == "system" and not service_user:
        raise click.ClickException("system scope requires --user")

    environment = current_display_environment()
    values["display"] = (
        values.get("display") or display or environment["display"]
    )
    values["wayland_display"] = (
        values.get("wayland_display")
        or wayland_display
        or environment["wayland_display"]
    )
    values["runtime_dir"] = (
        values.get("runtime_dir") or runtime_dir or environment["runtime_dir"]
    )
    unit = render_unit(
        scope=scope,
        user=service_user,
        display=values["display"],
        wayland_display=values["wayland_display"],
        runtime_dir=values["runtime_dir"],
    )
    if dry_run:
        click.echo(unit, nl=False)
        return

    try:
        config_path = dump_config(config_name, values)
        path = install_unit(unit, scope, enable, start, config_name)
    except (ConfigError, OSError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Wrote {config_path}")
    click.echo(f"Installed {path}")


@service.command(name="show-unit")
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
@click.option("--user", "service_user")
@click.option("--display")
@click.option("--wayland-display")
@click.option("--runtime-dir")
def service_show_unit(
    scope, service_user, display, wayland_display, runtime_dir
):
    """Print generated templated systemd unit."""
    environment = current_display_environment()
    click.echo(
        render_unit(
            scope=scope,
            user=service_user,
            display=display or environment["display"],
            wayland_display=wayland_display or environment["wayland_display"],
            runtime_dir=runtime_dir or environment["runtime_dir"],
        ),
        nl=False,
    )


@service.command(name="uninstall")
@click.option("--config", "config_name", default="config", show_default=True)
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
def service_uninstall(config_name, scope):
    """Stop, disable, and remove one service instance."""
    try:
        uninstall_unit(scope, config_name)
    except (OSError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        f"Removed {service_instance_name(config_name)} ({scope} scope)."
    )


@service.command(name="status")
@click.option("--config", "config_name", default="config", show_default=True)
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
def service_status(config_name, scope):
    """Show systemd service status."""
    try:
        result = run_systemctl(
            scope,
            "status",
            service_instance_name(config_name),
            "--no-pager",
            check=False,
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    raise click.exceptions.Exit(result.returncode)


@service.command(name="start")
@click.option("--config", "config_name", default="config", show_default=True)
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
def service_start(config_name, scope):
    """Start service."""
    _run_service_action(scope, "start", config_name)


@service.command(name="stop")
@click.option("--config", "config_name", default="config", show_default=True)
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
def service_stop(config_name, scope):
    """Stop service."""
    _run_service_action(scope, "stop", config_name)


@service.command(name="restart")
@click.option("--config", "config_name", default="config", show_default=True)
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
def service_restart(config_name, scope):
    """Restart service."""
    _run_service_action(scope, "restart", config_name)


@service.command(name="enable")
@click.option("--config", "config_name", default="config", show_default=True)
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
def service_enable(config_name, scope):
    """Enable service at user/system target."""
    _run_service_action(scope, "enable", config_name)


@service.command(name="disable")
@click.option("--config", "config_name", default="config", show_default=True)
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
def service_disable(config_name, scope):
    """Disable service at user/system target."""
    _run_service_action(scope, "disable", config_name)


@service.command(name="logs")
@click.option("--config", "config_name", default="config", show_default=True)
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
@click.option("--follow", is_flag=True)
@click.option(
    "--lines", type=click.IntRange(min=1), default=100, show_default=True
)
def service_logs(config_name, scope, follow, lines):
    """Show service journal logs."""
    try:
        result = run_journalctl(
            scope, follow=follow, lines=lines, config_name=config_name
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    raise click.exceptions.Exit(result.returncode)


@service.command(name="doctor")
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
def service_doctor(scope):
    """Check systemd service readiness."""
    results = run_checks(require_persistent=True, include_service=True)
    results.append(service_unit_check(scope))
    _print_checks(results)
    if any(result.level == "fail" for result in results):
        raise click.exceptions.Exit(1)


def _run_service_action(scope: str, action: str, config_name: str):
    try:
        run_systemctl(scope, action, service_instance_name(config_name))
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc


def _require_stable_install(allow_ephemeral: bool):
    error = stable_install_error(allow_ephemeral)
    if error:
        raise click.ClickException(error)


def _print_checks(results):
    for result in results:
        if result.level == "ok":
            marker = click.style("OK", fg="green")
        elif result.level == "warn":
            marker = click.style("WARN", fg="yellow")
        else:
            marker = click.style("FAIL", fg="red")
        click.echo(f"[{marker}] {result.name}: {result.detail}")
