# Remote Screen Control Plan

Status: planned, not implemented.

## Scope

Support four intentionally limited remote commands:

- `screen_on`
- `screen_off`
- `follow_schedule`
- `restart_agent`

No arbitrary shell, browser, display, or CEC commands will be exposed.

## State model

Keep configured RRULE schedules unchanged. Add persistent remote-control state to
`Screen`:

- `power_override`: nullable choice `on` / `off`; null means follow schedule.
- `reported_power_state`: nullable choice `on` / `off` / `unknown`.
- `reported_power_at`: timestamp for last agent report.

Compute, do not persist, `desired_power_state`:

1. `power_override=on` => `on`.
2. `power_override=off` => `off`.
3. Otherwise evaluate `on_schedule` and `off_schedule`; latest applicable
   occurrence wins.
4. No applicable schedule occurrence => null/unknown; agent leaves CEC state
   unchanged.

Successful agent CEC commands update reported state. Failed commands keep the
previous report and emit an agent warning. A startup report/re-evaluation must
not assume display state from process-local memory.

## Restart command delivery

Use a small one-shot `ScreenCommand` model rather than a boolean restart flag:

- UUID primary key.
- Screen foreign key.
- command choice, currently only `restart_agent`.
- created, acknowledged timestamps.

Only the newest unacknowledged command is exposed to an agent. Agent
acknowledges before exiting; systemd `Restart=always` starts it again. Matching
UUID acknowledgement makes restart delivery idempotent and prevents restart
loops after process startup.

## Manager API

Admin is the only remote control surface. No public control endpoint will be
added. Extend existing screen configuration response with:

```json
{
  "power_override": "on" | "off" | null,
  "desired_power_state": "on" | "off" | null,
  "reported_power_state": "on" | "off" | "unknown" | null,
  "reported_power_at": "..." | null,
  "pending_command": {"id": "uuid", "command": "restart_agent"} | null
}
```

Add only an agent state-report endpoint, using existing screen public token as
agent credential:

- `POST /api/screens/<token>/state`
  - accepts actual power state and optional command UUID acknowledgement.
  - updates report fields and acknowledges only the matching pending command.

Admin actions are the only way to set overrides or create restart commands. No
endpoint accepts remote control commands, raw CEC input, or arbitrary agent
actions.

## Admin UI

Add a `REMOTE CONTROL` fieldset and four object actions to `ScreenAdmin`:

- Screen on: set override `on`.
- Screen off: set override `off`.
- Follow schedule: clear override.
- Restart agent: create one-shot restart command.

Show override, desired state, reported state, and report timestamp as readonly
fields. Existing schedule and preload fieldsets remain unchanged.

## Agent changes

- Extend `ManagerClient` parsing with power state and pending command data.
- Add `ManagerClient.report_state()` for the state endpoint.
- Replace process-local schedule-only decision with server-provided desired state;
  retain local RRULE parsing only if needed as a validation/fallback path.
- On every startup and after every config poll:
  - apply desired `on`/`off` through `CecController` if it differs from the
    agent's last successfully reported state;
  - report successful/unknown state to Manager.
- If pending command is `restart_agent`, report acknowledgement, then exit
  cleanly so systemd restarts the process. Direct runs also exit rather than
  invoking arbitrary process-control commands.
- Keep CEC failures retryable and visible in logs; never crash playlist control
  solely because a CEC command failed.

## Migrations and tests

Add migrations for `Screen` state fields and `ScreenCommand`. Test:

- override precedence over schedule;
- follow schedule clearing override;
- latest schedule occurrence calculation;
- command validation and one-shot acknowledgement;
- reported state updates and timestamps;
- API authorization/token behavior and response shape;
- admin actions;
- agent startup re-evaluation after restart;
- CEC on/off calls, retry behavior, and restart acknowledgement;
- no duplicate restart after acknowledgement.

Run Django and agent suites, migration checks, Ruff, Pyright, and lens
 diagnostics before deployment. Do not deploy to board until requested.

## Decision

Admin-only control surface selected. Existing public token is used only for
agent configuration reads and state reports; control commands are issued from
authenticated Django admin actions.
