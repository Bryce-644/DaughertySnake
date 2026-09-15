# Battlesnake — "Daugherty"

Entry for the Vasion Battlesnake Funathon. Built on the official
[Python starter](https://github.com/BattlesnakeOfficial/starter-snake-python);
all decision logic is in `main.py`, and `server.py` is the starter's Flask shim,
unmodified.

## Layout

| Path | What it is |
| --- | --- |
| `main.py` | The snake. Everything worth changing is here. |
| `server.py` | Starter Flask shim — routes, binds `0.0.0.0`, honours `$PORT`. Don't edit. |
| `play.ps1` | Runs local games and prints a summary. |
| `tests\test_main.py` | Unit tests, including regressions for bugs found in self-play. |
| `tools\battlesnake.exe` | Battlesnake CLI v1.2.3. |
| `.venv\` | Python 3.12 virtualenv. |

Note: the `python` on PATH is a broken Microsoft Store stub. Always use
`.\.venv\Scripts\python.exe`.

## Run it

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q     # unit tests
.\.venv\Scripts\python.exe main.py                # serve on :8000

.\play.ps1                        # 10 solo games
.\play.ps1 -Games 25 -Snakes 4    # 25 four-way self-play games
.\play.ps1 -Games 1 -Browser      # one game, watched in the browser
```

`play.ps1` starts and stops the server itself. It flags any game ending by turn 3,
which means a hard safety bug rather than bad luck.

## How the snake decides

Every candidate move is scored and the highest wins. Four layers:

1. **Hard safety** — discard off-board squares and any square still occupied when
   we arrive. Occupancy is *time-aware*: a segment `i` back from the head of an
   `n`-long snake vacates in `n - i` turns, so the tail square is legal to enter.
   This is what lets the snake chase its own tail down a one-wide corridor.
2. **Space** — flood fill from each candidate using those same timers, with a
   heavy penalty when reachable space is smaller than our own length. This is the
   highest-value layer; it's what stops the snake boxing itself in.
3. **Food** — BFS distance to nearest reachable food, weighted by health (urgent
   below 30, moderate below 60) and bumped when we're the shortest snake.
4. **Head to head** — squares a same-length-or-longer snake could also reach are
   heavily penalised, counted per threat; squares only a *shorter* snake can reach
   get a bonus, because we win that collision.

Two subtleties that cost real games in testing, both now covered by tests:

- **Contested food is not a length advantage.** If the contested square is food,
  the opponent eats it too and grows by the same 1, so the head-to-head
  comparison uses raw lengths. Crediting ourselves a `+1` turned mutual kills
  into phantom wins and produced 12 draws in 25 self-play games.
- **Don't apply "might grow" pessimism to our own snake.** We know whether the
  move being evaluated eats, so our own tail timing is exact. Being pessimistic
  about it wrongly blocked our own tail square and, in tight spots, left only
  fatal options.

No multi-turn lookahead. It risks the 500 ms move budget and is much harder to
debug mid-tournament; revisit only if the snake is clearly outclassed.

## Measured performance

11×11, 25-game batches, Python 3.12 on this machine:

| Scenario | Avg turns | Min | Worst ms/turn |
| --- | --- | --- | --- |
| Solo | ~640 | 322 | 15 |
| 4-way self-play | ~115 | 30 | 37 |

`ms/turn` covers every snake's HTTP round trip, so per-move cost is roughly a
quarter of the four-snake figure — far inside the 500 ms budget.

## Tuning between rounds

The knobs are named constants at the top of `main.py`:

| Constant | Raise it to... |
| --- | --- |
| `W_SPACE` | play more cautiously, value open board more |
| `W_TRAP_BASE`, `W_TRAP_PER_CELL` | avoid pockets harder (more negative) |
| `W_H2H_WIN` | hunt smaller snakes more aggressively |
| `W_H2H_LOSS` | dodge bigger snakes harder (more negative) |
| `HUNGRY_HEALTH`, `PECKISH_HEALTH` | start seeking food sooner |
| `W_CENTER` | fight harder for centre control (more negative) |

Change one at a time and re-run `.\play.ps1 -Games 25 -Snakes 4`; compare average
turns. Always re-run the unit tests before publishing.

## Deploy to Replit

1. Open the starter as a Replit template via the **Run on Replit** badge on the
   [starter repo](https://github.com/BattlesnakeOfficial/starter-snake-python).
2. Replace the contents of `main.py` with this repo's `main.py`. Leave
   `server.py` and `requirements.txt` alone — nothing else needs to change.
3. Run, then **Publish**.

Replit gotchas from the participant guide:

- Changes don't show in the preview until you restart the service —
  `Cmd+K` → "Restart compute".
- Changes aren't live for tournaments until you **republish**.
- Idle apps go to sleep. Hit the endpoint at least **5 minutes** before any
  tournament, and check early if you haven't touched it since the day before.

## Register

On [battlesnake.com](https://battlesnake.com), create a snake pointing at the
published Replit URL. The display name **must contain "Daugherty"** per the event
rules. Verify by opening the URL in a browser — you should see the `info()` JSON.

Set `author` in `main.py` to your battlesnake.com username if you want it to
match; it's cosmetic and doesn't affect play.
