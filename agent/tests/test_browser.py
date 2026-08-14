from unittest.mock import Mock

import kiosk_agent.browser as browser_module
from kiosk_agent.browser import BrowserController


def _launch_args(monkeypatch, environment, profile_dir):
    monkeypatch.setattr(
        browser_module,
        "find_browser",
        lambda _command: "/usr/bin/chromium",
    )
    popen = Mock()
    monkeypatch.setattr(browser_module.subprocess, "Popen", popen)
    for name in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    controller = BrowserController(
        browser="chromium",
        cdp_url="http://127.0.0.1:9222",
        profile_dir=profile_dir,
    )
    monkeypatch.setattr(
        BrowserController,
        "_wait_for_page",
        lambda _controller: {
            "webSocketDebuggerUrl": "ws://127.0.0.1/devtools"
        },
    )
    monkeypatch.setattr(
        BrowserController,
        "_send_command",
        lambda _controller, _method: None,
    )
    monkeypatch.setattr(
        browser_module.websocket,
        "create_connection",
        Mock(return_value=Mock()),
    )
    controller.start()
    return popen.call_args.args[0]


def test_browser_launch_selects_wayland_and_basic_password_store(
    monkeypatch, tmp_path
):
    command = _launch_args(
        monkeypatch,
        {
            "WAYLAND_DISPLAY": "wayland-0",
            "XDG_RUNTIME_DIR": "/run/user/1000",
        },
        tmp_path,
    )

    assert "--ozone-platform=wayland" in command
    assert "--remote-allow-origins=http://127.0.0.1:9222" in command
    assert "--password-store=basic" in command


def test_browser_launch_selects_x11(monkeypatch, tmp_path):
    command = _launch_args(monkeypatch, {"DISPLAY": ":0"}, tmp_path)

    assert "--ozone-platform=x11" in command
