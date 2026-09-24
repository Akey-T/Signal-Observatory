# P0-C scheduler v2 readiness — 2026-09-24 UTC

## Initial inspection (before owner approval)

The following snapshot was inspection only. At that point no Windows power plan, Docker Desktop
setting, startup entry, Worker schedule, historical scheduler row, or qualification marker had been
changed.

| Check                        | Current evidence                                                                                                                                                                                   |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Historical punctuality v1    | `failed`: 3/3 terminal windows, 0 on time, 3 late; immutable                                                                                                                                       |
| Rolling seven-day continuity | `failed`: seven rows, 0 missing, 0 duplicates, 1 missed/interrupted                                                                                                                                |
| Next planned arXiv window    | `2026-09-25T02:00:00Z`, currently pending                                                                                                                                                          |
| Compose                      | `db`, `api`, `worker`, `web` healthy after 2026-09-24 rebuild; all services specify `restart: unless-stopped`                                                                                      |
| Windows power                | Balanced plan; S0 modern standby and hibernation available; automatic sleep after 3,600 seconds on AC and 1,800 seconds on battery; automatic hibernate timeout disabled                           |
| Docker startup               | Docker Desktop processes are running; `com.docker.service` reports stopped/manual; no per-user Run key was visible in the inspected HKCU path. Reliable post-reboot auto-start is not established. |
| Reboot evidence              | `Get-CimInstance Win32_OperatingSystem` was access-denied; no reboot claim made                                                                                                                    |
| Code contract                | `scheduler-punctuality-v1` is hard-coded in the Worker plan marker and read-only verifier. A v2 code change and tests are needed to isolate a fresh sequence.                                      |

The current AC sleep setting can suspend the host well before a `02:00 UTC` due window. The
specific proposed change is `powercfg /change standby-timeout-ac 0` (disable automatic sleep only
while connected to AC); battery sleep remains 30 minutes. Risk: additional energy consumption and
heat while plugged in. Reversal: `powercfg /change standby-timeout-ac 60`. The owner must approve
this OS-level change and ensure the machine remains powered, Docker Desktop is available, and the
Worker runs across the qualifying windows. Docker auto-start/reboot behavior should be confirmed
before claiming unattended recovery.

## Owner-approved follow-up (2026-09-24)

The owner approved keeping the plugged-in computer awake while allowing its screen to turn off.
`powercfg /change standby-timeout-ac 0` was applied. A subsequent read-only query confirmed the
active Balanced plan has AC automatic sleep disabled (`STANDBYIDLE = 0`), while battery automatic
sleep remains 1,800 seconds. Display-off timeout was not changed: 3,600 seconds on AC and 1,800
seconds on battery. Display off is distinct from dimming or system sleep. This setting can be
reversed with `powercfg /change standby-timeout-ac 60`. It does not establish Docker auto-start
after reboot, prevent lid-close sleep, or protect against power loss.

The smallest versioned code change deployed `scheduler-punctuality-v2` for newly planned windows
and made the verifier skip an already-planned future v1 window when reporting the next v2 window.
The persisted 2026-09-25 02:00 UTC plan remains v1 and was not retagged. The first _eligible_ v2
window is 2026-09-26 02:00 UTC, subject to the Worker actually planning and executing it. No
historical v1 outcome or scheduler row was changed. Four Compose services (`db`, `api`, `worker`,
`web`) were healthy after the rebuilt deployment.

Post-deployment read-only verification reported v2 `PENDING`, 0/3 completed qualifying windows,
and `modified_records = 0`. Rolling seven-day continuity remained `FAILED` because the existing
seven-day evidence included one missed/interrupted window. The current result is **not** a v2
acceptance. Three consecutive real v2 scheduled dispatches must each be at most 300 seconds late,
and seven consecutive real natural daily windows must have no missing, duplicate, missed, or
interrupted row. Manual collection cannot satisfy either sequence; collector outcome remains
independent of dispatch punctuality.

Focused scheduler tests passed (22); full Python tests passed (216, with two environment-dependent
skips). Ruff lint/format, mypy, frontend lint/format/typecheck/tests/build, and `docker compose
config` passed. The four services were healthy after `docker compose up -d --build`. Future daily
evidence, rather than this deployment check, determines whether v2 and continuity eventually pass.
