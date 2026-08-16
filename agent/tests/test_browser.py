import json
import logging
import time
from unittest.mock import Mock

import kiosk_agent.browser as browser_module
from kiosk_agent.browser import BrowserController, BrowserError


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
        lambda _controller, _target_id=None, **_kwargs: {
            "id": _target_id or "initial-target",
            "webSocketDebuggerUrl": "ws://127.0.0.1/devtools",
        },
    )
    monkeypatch.setattr(
        BrowserController,
        "_browser_command",
        lambda _controller, method, _params=None: (
            {"targetInfos": []}
            if method == "Target.getTargets"
            else {"targetId": "initial-target"}
        ),
    )
    monkeypatch.setattr(
        BrowserController,
        "_send_command",
        lambda _controller, _method: None,
    )
    focus_emulation = Mock()
    monkeypatch.setattr(
        BrowserController,
        "_enable_focus_emulation",
        lambda _controller, socket: focus_emulation(socket),
    )
    monkeypatch.setattr(
        browser_module.websocket,
        "create_connection",
        Mock(return_value=Mock()),
    )
    controller.start()
    return popen.call_args.args[0], focus_emulation


def test_browser_launch_selects_wayland_and_basic_password_store(
    monkeypatch, tmp_path
):
    command, focus_emulation = _launch_args(
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
    assert "--hide-scrollbars" in command
    focus_emulation.assert_called_once()
    assert "--disable-background-timer-throttling" in command
    assert "--disable-backgrounding-occluded-windows" in command
    assert "--disable-renderer-backgrounding" in command


def test_browser_launch_selects_x11(monkeypatch, tmp_path):
    command, _ = _launch_args(monkeypatch, {"DISPLAY": ":0"}, tmp_path)

    assert "--ozone-platform=x11" in command


def test_preload_finishes_on_load_event(caplog, tmp_path):
    controller = BrowserController(
        browser="chromium",
        cdp_url="http://127.0.0.1:9222",
        profile_dir=tmp_path,
    )
    socket = Mock()
    socket.recv.return_value = json.dumps({"method": "Page.loadEventFired"})

    caplog.set_level(logging.DEBUG, logger="kiosk_agent.browser")
    method_name = "_navigate_and_wait"
    navigate_and_wait = getattr(controller, method_name)
    navigate_and_wait(socket, "https://example.test", 0, 30)

    assert "preload_delay_seconds=0.0" in caplog.text
    assert "result=loaded" in caplog.text


def test_content_injections_install_before_navigation(monkeypatch, tmp_path):
    controller = BrowserController(
        browser="chromium",
        cdp_url="http://127.0.0.1:9222",
        profile_dir=tmp_path,
    )
    calls = []
    monkeypatch.setattr(
        BrowserController,
        "_send_socket_command",
        lambda _controller, _socket, method, params=None: calls.append(
            (method, params)
        ),
    )

    controller._install_injections(  # pyright: ignore[reportPrivateUsage]
        Mock(),
        "body { color: red; }",
        "window.beforeRan = true;",
        "window.afterRan = true;",
    )

    assert [method for method, _params in calls] == [
        "Page.addStyleToEvaluateOnNewDocument",
        "Page.addScriptToEvaluateOnNewDocument",
    ]
    script = calls[1][1]["source"]
    assert "window.beforeRan = true;" in script
    assert "window.afterRan = true;" in script
    assert "javascript_before" in script
    assert "javascript_after" in script


def test_css_injection_uses_script_fallback_for_unsupported_cdp(
    monkeypatch, caplog, tmp_path
):
    controller = BrowserController(
        browser="chromium",
        cdp_url="http://127.0.0.1:9222",
        profile_dir=tmp_path,
    )
    calls = []

    def send_command(_controller, _socket, method, params=None):
        calls.append((method, params))
        if method == "Page.addStyleToEvaluateOnNewDocument":
            raise BrowserError(
                "{'code': -32601, 'message': 'Method not found'}"
            )

    monkeypatch.setattr(
        BrowserController,
        "_send_socket_command",
        send_command,
    )

    caplog.set_level(logging.DEBUG, logger="kiosk_agent.browser")
    controller._install_injections(  # pyright: ignore[reportPrivateUsage]
        Mock(),
        "body { color: red; }",
        None,
        None,
    )

    assert [method for method, _params in calls] == [
        "Page.addStyleToEvaluateOnNewDocument",
        "Page.addScriptToEvaluateOnNewDocument",
    ]
    assert "body { color: red; }" in calls[1][1]["source"]
    assert "CSS injection installation failed" not in caplog.text


def test_current_css_is_applied_to_loaded_document(monkeypatch, tmp_path):
    controller = BrowserController(
        browser="chromium",
        cdp_url="http://127.0.0.1:9222",
        profile_dir=tmp_path,
    )
    calls = []
    monkeypatch.setattr(
        BrowserController,
        "_send_socket_command",
        lambda _controller, _socket, method, params=None: calls.append(
            (method, params)
        ),
    )

    controller._install_current_css(  # pyright: ignore[reportPrivateUsage]
        Mock(),
        ".public-dashboard-footer { display: none !important; }",
    )

    assert calls[0][0] == "Runtime.evaluate"
    expression = calls[0][1]["expression"]
    assert "kiosk-agent-injected-css" in expression
    assert "public-dashboard-footer" in expression


def test_numeric_preload_logs_load_event(caplog, tmp_path):
    controller = BrowserController(
        browser="chromium",
        cdp_url="http://127.0.0.1:9222",
        profile_dir=tmp_path,
    )
    socket = Mock()
    socket.recv.return_value = json.dumps({"method": "Page.loadEventFired"})

    caplog.set_level(logging.DEBUG, logger="kiosk_agent.browser")
    controller._navigate_and_wait(  # pyright: ignore[reportPrivateUsage]
        socket,
        "https://example.test",
        7,
        30,
    )

    load_records = [
        record
        for record in caplog.records
        if "page load" in record.getMessage()
    ]
    assert load_records
    assert all(record.levelno == logging.DEBUG for record in load_records)


def test_javascript_dialog_policy(monkeypatch, tmp_path):
    controller = BrowserController(
        browser="chromium",
        cdp_url="http://127.0.0.1:9222",
        profile_dir=tmp_path,
    )
    calls = []
    monkeypatch.setattr(
        BrowserController,
        "_send_socket_command",
        lambda _controller, _socket, method, params=None: calls.append(
            (method, params)
        ),
    )
    socket = Mock()

    for dialog_type, expected_accept in (
        ("alert", True),
        ("confirm", False),
        ("prompt", False),
        ("beforeunload", True),
    ):
        controller._handle_dialog_event(  # pyright: ignore[reportPrivateUsage]
            socket,
            {"params": {"type": dialog_type, "message": "hello"}},
        )
        assert calls[-1][0] == "Page.handleJavaScriptDialog"
        assert calls[-1][1] == {"accept": expected_accept}


def test_numeric_preload_waits_from_load_event(monkeypatch, caplog, tmp_path):
    controller = BrowserController(
        browser="chromium",
        cdp_url="http://127.0.0.1:9222",
        profile_dir=tmp_path,
    )
    socket = Mock()
    job = browser_module._PreloadJob(  # pyright: ignore[reportPrivateUsage]
        "job",
        "https://example.test",
        30,
        preload_delay_seconds=7,
    )
    job.cancelled = Mock()
    wait_for_dialogs = Mock(return_value=False)
    monkeypatch.setattr(
        BrowserController,
        "_wait_with_dialogs",
        wait_for_dialogs,
    )
    monkeypatch.setattr(
        BrowserController,
        "_create_preload_target",
        lambda _controller: ("target", socket),
    )
    monkeypatch.setattr(
        BrowserController,
        "_send_socket_command",
        lambda *_args: {},
    )
    monkeypatch.setattr(
        BrowserController,
        "_enable_focus_emulation",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        BrowserController,
        "_navigate_and_wait",
        lambda *_args: True,
    )
    caplog.set_level(logging.DEBUG, logger="kiosk_agent.browser")

    controller._load_preload(job)  # pyright: ignore[reportPrivateUsage]

    wait_for_dialogs.assert_called_once_with(socket, job.cancelled, 7)
    assert "preload delay elapsed" in caplog.text


def test_preload_delay_cannot_extend_request_timeout(monkeypatch, tmp_path):
    controller = BrowserController(
        browser="chromium",
        cdp_url="http://127.0.0.1:9222",
        profile_dir=tmp_path,
    )
    socket = Mock()
    job = browser_module._PreloadJob(  # pyright: ignore[reportPrivateUsage]
        "job",
        "https://example.test",
        0.01,
        preload_delay_seconds=10,
    )
    job.cancelled = Mock()
    wait_for_dialogs = Mock(return_value=False)
    monkeypatch.setattr(
        BrowserController,
        "_wait_with_dialogs",
        wait_for_dialogs,
    )
    monkeypatch.setattr(
        BrowserController,
        "_create_preload_target",
        lambda _controller: ("target", socket),
    )
    monkeypatch.setattr(
        BrowserController,
        "_send_socket_command",
        lambda *_args: {},
    )
    monkeypatch.setattr(
        BrowserController,
        "_enable_focus_emulation",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        BrowserController,
        "_navigate_and_wait",
        lambda *_args: True,
    )

    controller._load_preload(job)  # pyright: ignore[reportPrivateUsage]

    assert wait_for_dialogs.call_args.args[2] < 0.1


def test_numeric_preload_does_not_wait_for_timeout_after_load_event(tmp_path):
    controller = BrowserController(
        browser="chromium",
        cdp_url="http://127.0.0.1:9222",
        profile_dir=tmp_path,
    )
    socket = Mock()
    messages = [json.dumps({"method": "Page.loadEventFired"})]

    def receive():
        if messages:
            return messages.pop()
        raise browser_module.websocket.WebSocketTimeoutException()

    socket.recv.side_effect = receive
    method_name = "_navigate_and_wait"
    navigate_and_wait = getattr(controller, method_name)
    started = time.monotonic()
    navigate_and_wait(socket, "https://example.test", 0.01, 1)

    assert time.monotonic() - started < 0.5


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
        lambda *_args: None,
    )
    monkeypatch.setattr(
        browser_module.websocket,
        "create_connection",
        Mock(return_value=new_socket),
    )

    controller.navigate(
        "https://example.test",
        preload_delay_seconds=0,
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
