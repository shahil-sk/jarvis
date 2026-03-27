# Scheduler Plugin

Background reminder engine. Fires desktop notifications + prints to terminal.
Persisted in `~/.jarvis/memory.db` — survives restarts (pending reminders reload on boot).

## Commands

```
remind me in 10 minutes to call John
remind me in 2 hours check the build
remind me in 30 seconds test
schedule daily remind me to drink water
schedule hourly check server stats
list reminders
cancel reminder 3
```

## Repeat Modes
| Phrase | Interval |
|---|---|
| `every minute` / `minutely` | 60s |
| `every hour` / `hourly` | 1h |
| `every day` / `daily` | 24h |

## How It Works
- On plugin load, a **daemon thread** starts polling the DB every 5 seconds
- Due reminders fire a desktop notification + print to terminal inline
- Repeating reminders auto-reschedule themselves in the DB
- One-shot reminders are marked `done=1` after firing
