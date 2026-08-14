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


def test_preload_activates_new_target(monkeypatch, tmp_path):
    controller = BrowserController(
        browser="chromium",
        cdp_url="http://127.0.0.1:9222",
        profile_dir=tmp_path,
    )
    old_socket = Mock()
    new_socket = Mock()
    object.__setattr__(controller, "_socket", old_socket)
    object.__setattr__(controller, "_target_id", "old-target")
    browser_commands = []

    def browser_command(_controller, method, params=None):
        browser_commands.append((method, params))
        if method == "Target.createTarget":
            return {"targetId": "new-target"}
        return {}

    monkeypatch.setattr(BrowserController, "_browser_command", browser_command)
    monkeypatch.setattr(
        BrowserController,
        "_wait_for_page",
        lambda _controller, target_id: {
            "id": target_id,
            "webSocketDebuggerUrl": "ws://127.0.0.1/new",
        },
    )
    monkeypatch.setattr(
        BrowserController,
        "_send_socket_command",
        lambda _controller, _socket, _method, _params=None: {},
    )
    monkeypatch.setattr(
        BrowserController,
        "_navigate_and_wait",
        lambda _controller, _socket, _url, _seconds, _timeout: None,
    )
    monkeypatch.setattr(
        browser_module.websocket,
        "create_connection",
        Mock(return_value=new_socket),
    )

    controller.navigate(
        "https://example.test",
        preload_seconds="auto",
        preload_timeout_seconds=30,
    )

    assert object.__getattribute__(controller, "_socket") is new_socket
    assert object.__getattribute__(controller, "_target_id") == "new-target"
    assert old_socket.close.called
    assert browser_commands == [
        ("Target.createTarget", {"url": "about:blank", "background": True}),
        ("Target.activateTarget", {"targetId": "new-target"}),
        ("Target.closeTarget", {"targetId": "old-target"}),
    ]
