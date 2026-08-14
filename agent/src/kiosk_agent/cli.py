import json
import logging
import os
import tempfile
from pathlib import Path

import click

from . import __version__
from .api import ManagerClient, ManagerError
from .browser import BrowserController, BrowserError
from .diagnostics import run_checks, service_unit_check
from .paths import ensure_profile_dir
from .runner import AgentRunner
from .service import (
    SERVICE_NAME,
    current_display_environment,
    install_unit,
    render_unit,
    run_journalctl,
    run_systemctl,
    stable_install_error,
    uninstall_unit,
)

DEFAULT_CDP_URL = "http://127.0.0.1:9222"


@click.group()
@click.version_option(version=__version__)
def main():
    """Run and manage Kiosk Agent."""


@main.command()
@click.option("--manager", required=True, help="Kiosk Manager base URL.")
@click.option("--screen", "screen_token", required=True, help="Screen token.")
@click.option("--browser", default=None, help="Chromium executable name/path.")
@click.option("--cdp-url", default=DEFAULT_CDP_URL, show_default=True)
@click.option("--profile-dir", type=click.Path(path_type=Path))
@click.option("--ephemeral-profile", is_flag=True)
@click.option("--launch-browser/--no-launch-browser", default=True)
@click.option(
    "--poll-interval",
    type=click.FloatRange(min=1),
    default=15.0,
    show_default=True,
)
def run(
    manager,
    screen_token,
    browser,
    cdp_url,
    profile_dir,
    ephemeral_profile,
    launch_browser,
    poll_interval,
):
    """Launch Chromium and run screen playlist."""
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

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    runner = AgentRunner(
        ManagerClient(manager, screen_token),
        BrowserController(browser, cdp_url, profile, launch_browser),
        poll_interval,
    )
    try:
        runner.run()
    except (BrowserError, ManagerError) as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        if temporary_profile is not None:
            temporary_profile.cleanup()


@main.command()
@click.option("--manager", help="Kiosk Manager base URL.")
@click.option("--screen", "screen_token", help="Screen token.")
@click.option("--browser", default=None, help="Chromium executable name/path.")
@click.option("--cdp-url", default=DEFAULT_CDP_URL, show_default=True)
def doctor(manager, screen_token, browser, cdp_url):
    """Check agent, browser, display, systemd, and manager readiness."""
    if bool(manager) != bool(screen_token):
        raise click.UsageError("--manager and --screen must be used together")
    results = run_checks(
        manager_url=manager,
        screen_token=screen_token,
        cdp_url=cdp_url,
        browser=browser,
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
                    "items": [
                        {
                            "url": item.url,
                            "duration_seconds": item.duration_seconds,
                            "order": item.order,
                        }
                        for item in config.items
                    ],
                },
                indent=2,
            )
        )
        return

    click.echo(f"Version: {config.version}")
    if not config.items:
        click.echo("Playlist is empty.")
        return
    for item in config.items:
        click.echo(f"{item.order}. {item.url} ({item.duration_seconds:g}s)")


@main.group()
def service():
    """Manage systemd service installation and lifecycle."""


@service.command(name="install")
@click.option("--manager", required=True, help="Kiosk Manager base URL.")
@click.option("--screen", "screen_token", required=True, help="Screen token.")
@click.option("--browser", default="chromium", show_default=True)
@click.option("--cdp-url", default=DEFAULT_CDP_URL, show_default=True)
@click.option("--profile-dir", type=click.Path(path_type=Path))
@click.option("--ephemeral-profile", is_flag=True)
@click.option("--launch-browser/--no-launch-browser", default=True)
@click.option(
    "--poll-interval",
    type=click.FloatRange(min=1),
    default=15.0,
    show_default=True,
)
@click.option(
    "--scope",
    type=click.Choice(["user", "system"]),
    default="user",
    show_default=True,
)
@click.option("--user", "service_user")
@click.option("--display")
@click.option("--wayland-display")
@click.option("--runtime-dir")
@click.option("--enable/--no-enable", default=True, show_default=True)
@click.option("--start/--no-start", default=True, show_default=True)
@click.option("--allow-ephemeral", is_flag=True)
def service_install(
    manager,
    screen_token,
    browser,
    cdp_url,
    profile_dir,
    ephemeral_profile,
    launch_browser,
    poll_interval,
    scope,
    service_user,
    display,
    wayland_display,
    runtime_dir,
    enable,
    start,
    allow_ephemeral,
):
    """Install and optionally start user or system service."""
    _require_stable_install(allow_ephemeral)
    if scope == "system" and os.geteuid() != 0:
        raise click.ClickException("system scope requires root")
    if scope == "system" and not service_user:
        raise click.ClickException("system scope requires --user")

    environment = current_display_environment()
    unit = render_unit(
        scope=scope,
        manager=manager,
        screen=screen_token,
        browser=browser,
        cdp_url=cdp_url,
        poll_interval=poll_interval,
        profile_dir=profile_dir,
        ephemeral_profile=ephemeral_profile,
        launch_browser=launch_browser,
        user=service_user,
        display=display or environment["display"],
        wayland_display=wayland_display or environment["wayland_display"],
        runtime_dir=runtime_dir or environment["runtime_dir"],
    )
    try:
        path = install_unit(unit, scope, enable, start)
    except (OSError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Installed {path}")
    if scope == "user":
        click.echo(
            "Graphical autologin starts user service; linger is optional."
        )


@service.command(name="show-unit")
@click.option("--manager", required=True, help="Kiosk Manager base URL.")
@click.option("--screen", "screen_token", required=True, help="Screen token.")
@click.option("--browser", default="chromium", show_default=True)
@click.option("--cdp-url", default=DEFAULT_CDP_URL, show_default=True)
@click.option("--profile-dir", type=click.Path(path_type=Path))
@click.option("--ephemeral-profile", is_flag=True)
@click.option("--launch-browser/--no-launch-browser", default=True)
@click.option("--poll-interval", type=click.FloatRange(min=1), default=15.0)
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
@click.option("--user", "service_user")
@click.option("--display")
@click.option("--wayland-display")
@click.option("--runtime-dir")
def service_show_unit(
    manager,
    screen_token,
    browser,
    cdp_url,
    profile_dir,
    ephemeral_profile,
    launch_browser,
    poll_interval,
    scope,
    service_user,
    display,
    wayland_display,
    runtime_dir,
):
    """Print generated systemd unit."""
    environment = current_display_environment()
    click.echo(
        render_unit(
            scope=scope,
            manager=manager,
            screen=screen_token,
            browser=browser,
            cdp_url=cdp_url,
            poll_interval=poll_interval,
            profile_dir=profile_dir,
            ephemeral_profile=ephemeral_profile,
            launch_browser=launch_browser,
            user=service_user,
            display=display or environment["display"],
            wayland_display=wayland_display or environment["wayland_display"],
            runtime_dir=runtime_dir or environment["runtime_dir"],
        ),
        nl=False,
    )


@service.command(name="uninstall")
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
def service_uninstall(scope):
    """Stop, disable, and remove service unit."""
    try:
        uninstall_unit(scope)
    except (OSError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Removed {SERVICE_NAME} ({scope} scope).")


@service.command(name="status")
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
def service_status(scope):
    """Show systemd service status."""
    try:
        result = run_systemctl(
            scope, "status", SERVICE_NAME, "--no-pager", check=False
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    raise click.exceptions.Exit(result.returncode)


@service.command(name="start")
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
def service_start(scope):
    """Start service."""
    _run_service_action(scope, "start")


@service.command(name="stop")
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
def service_stop(scope):
    """Stop service."""
    _run_service_action(scope, "stop")


@service.command(name="restart")
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
def service_restart(scope):
    """Restart service."""
    _run_service_action(scope, "restart")


@service.command(name="enable")
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
def service_enable(scope):
    """Enable service at user/system target."""
    _run_service_action(scope, "enable")


@service.command(name="disable")
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
def service_disable(scope):
    """Disable service at user/system target."""
    _run_service_action(scope, "disable")


@service.command(name="logs")
@click.option("--scope", type=click.Choice(["user", "system"]), default="user")
@click.option("--follow", is_flag=True)
@click.option(
    "--lines", type=click.IntRange(min=1), default=100, show_default=True
)
def service_logs(scope, follow, lines):
    """Show service journal logs."""
    try:
        result = run_journalctl(scope, follow=follow, lines=lines)
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


def _run_service_action(scope: str, action: str):
    try:
        run_systemctl(scope, action, SERVICE_NAME)
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
