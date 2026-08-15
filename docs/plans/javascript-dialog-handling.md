# JavaScript Dialog Handling Plan

Status: planned, not implemented.

## Goal

Unattended kiosk pages must never remain blocked by native browser dialogs.
Handle `alert`, `confirm`, `prompt`, and `beforeunload` dialogs automatically
without exposing a dialog-control setting in screen or content configuration.

## Default policy

Use CDP `Page.handleJavaScriptDialog` with a fixed safe policy:

- `alert`: accept/acknowledge (`accept: true`).
- `confirm`: dismiss (`accept: false`).
- `prompt`: dismiss (`accept: false`); never inject prompt text.
- `beforeunload`: accept (`accept: true`) so playlist navigation can proceed.
- Unknown dialog types: dismiss and log warning.

All dialog messages are treated as untrusted page data. Truncate or sanitize
messages before logging; never execute or interpolate them into commands.

## Browser integration

Enable `Page` events on every page target, including background preload targets.
Handle `Page.javascriptDialogOpening` immediately by sending
`Page.handleJavaScriptDialog` on the same target socket.

Cover all periods where a dialog can block:

1. During `Page.navigate` and load-event waiting: integrate handling into the
   existing CDP receive loop.
2. During preload delay: replace passive waiting with a short-timeout event pump
   that handles dialogs while preserving cancellation and timeout behavior.
3. While active content is displayed: expose a non-blocking
   `BrowserController.handle_pending_dialogs()` drain and call it from the
   playlist loop at its regular short interval.
4. During generic page-socket command waits: route unsolicited dialog events
   through the same handler rather than discarding them.

Keep command response/event reads serialized per websocket. Do not introduce
concurrent readers for one CDP socket. If dialog response fails because target
or browser connection disappeared, log it and let existing browser recovery
close/recreate the target; do not crash the agent solely because a dialog was
seen.

Dialog handling must also cover targets used by content CSS/JavaScript
injection. Injected JavaScript may call dialog APIs just like page-owned code.

## Agent behavior

Add structured logs containing dialog type, target/content URL, and a bounded
message. Log automatic policy decisions at info/debug level; response failures
at warning level.

Dialog handling is infrastructure, not content health:

- Never mark playlist item unhealthy because it opened a dialog.
- Never abandon a preload solely because dialog was auto-dismissed.
- Never wait for user input.
- Preserve existing navigation timeout and recovery semantics for unrelated
  CDP/navigation failures.

## Tests

Add browser tests for each dialog type and policy, including `beforeunload`.
Verify `Page.handleJavaScriptDialog` receives expected `accept` values and no
prompt text.

Test dialog events during:

- navigation;
- preload delay;
- active playlist display;
- command response waits;
- CSS/JavaScript-injected content.

Test unknown types, long messages, malformed events, closed sockets, and failed
responses. Confirm failed handling does not crash agent and existing recovery
remains available.

Run agent tests, Ruff, Pyright, and lens diagnostics. No board deployment during
this change.
