# Chain Reaction — Game-only build

**Three local human players. No AI, autoplay, MCTS, minimax or CP-SAT implementation.**

A playable desktop version of the Chain Reaction proposal, with the original-style
black arena, green wire grid, red/blue/green orbs, player panels, live status and
move log. Python is used for the deterministic engine and controller. Pygame is
the primary window/input backend. Pillow draws the shared visuals. An optional
Tk window adapter uses exactly the same engine, controller and renderer.

Team: **Mynul Hassan Mehadi (2207105)** · **Ahnaf Tajwar (2207104)** · **Al-Amin (1707055)**

## Start here

Install Python **3.10 or newer** first. Python 3.11–3.13 is a practical choice.
Extract the ZIP before running the game. Do not run it from inside an archive.

### macOS

Open Terminal in this folder and run:

```sh
bash start_mac.command
```

### Windows

Double-click `start_windows.bat`. Alternatively, open a terminal in this folder:

```bat
start_windows.bat
```

### Linux

```sh
bash start_linux.sh
```

The launchers create a local `.venv` and install `requirements.txt` when the
packages are missing. The first installation needs internet. The game itself
has no online services, accounts, API keys, external downloads or network calls.

### Manual installation

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

On Windows, activate with `.venv\Scripts\activate` instead of `source ...`.
Use `python` or `py -3` instead of `python3` as appropriate to your installation.
The dependency is `pygame-ce`; its Python import name is `pygame`. Use a clean
virtual environment rather than installing both `pygame` and `pygame-ce` together.

## How to play

1. Press **Start**. Red plays first, then Blue, then Green.
2. Click an empty cell or one already owned by the active player.
3. Place exactly one orb. A corner explodes at **2**, an edge at **3**, and an
   interior cell at **4**. Only up/right/down/left neighbours count.
4. An explosion sends one orb to each neighbour. The recipient cell and all its
   orbs become the attacking player's colour. Reactions can trigger more reactions.
5. No one is eliminated before all three players have taken an initial turn.
   After that, a colour with no orbs is eliminated and its turns are skipped.
6. The last surviving colour wins. It does not need to occupy every cell.

The initial board is empty. All three turns are controlled by a person using the
same mouse. There is **no hidden random bot**. The planned-agent labels are only
informational and explicitly marked as unimplemented.

### Controls

| Control | Action |
|---|---|
| Click a cell | Place one orb when it is legal and the match is running |
| Start / Pause / Resume, or Space / P | Start or pause/resume the match and animations |
| Step, or `.` | While a move is resolving, advance one explosion or commit the resolved move; pauses the match |
| Undo, or U | Undo the last completed move; during a cascade, cancel the entire pending move |
| Reset, or R | Clear the current board after confirmation; keep its settings |
| New match / board settings, or N | Choose a board size and optional draw cap |
| Speed, or F | Slow → Normal → Fast → Instant |
| Counts, or C | Show small numeric orb counts in addition to orb clusters |
| Save replay, or S | Write a JSON replay to the app's replay folder |
| Load save, or L | Restore and validate the most recent autosave after confirmation |
| How to play, H or F1 | Rules and a fixed cascade example |
| Arrow keys + Enter | Choose and play a cell without a mouse |
| F11 | Toggle fullscreen |
| Escape | Close a dialog, or pause a running match |
| Scroll over move log | Browse earlier moves |

**Step never selects a move.** In this no-AI build it inspects an already-started
cascade. When there is no pending move, choose a legal cell manually.

The status panel shows **human turn time**, excluding pause/dialog time and cascade
animation. It does not pretend to measure AI decision time.

## Example position

Use **How to play → Try a cascade example**, or:

```sh
python run.py --example
```

The example consists of 36 fixed, manually specified legal moves, replayed from
an empty board. It is not an AI match or benchmark. It replaces the current board;
export a replay first to preserve a position. Red is next. Click **A1** (top left)
to see five linked explosions. Pause and use Step to inspect the transitions.
The example is also included as `examples/cascade_example.json`.

## Settings and exact rule choices

- **Default: 6 columns × 9 rows.** The proposal did not fix dimensions. This is
  an implementation choice, with Compact 5×6 and Large 8×10 options.
- **No move-limit draw by default.** Optional 60- or 100-total-move caps are
  explicit extra tournament rules, not classic rules. A win takes precedence.
  Otherwise a draw is declared only after the final move has fully resolved.
- **No human timeout.** Equal AI decision budgets belong to the later AI phase.
- **Deterministic cascade order:** FIFO, adding neighbours in up/right/down/left
  order. A toppling subtracts its threshold; excess orbs are not erased.
- **Winning during a cascade:** after everyone has entered, stop once a complete
  atomic explosion leaves only one colour. Some winner-owned cells may still be
  full at that terminal moment. The match is over, so there is no next move.
- **Safety is not a draw:** an exact repeated cascade state (including queue order)
  or 10,000 topplings stops the run as **ABORTED**. The UI says “Safety stop”. It
  does not invent a winner or count the stop as a normal draw. Undo/reset remains
  available. This prevents a non-settling cascade from freezing the application.
- The engine never adds another real placement while a cascade is resolving.

## Saves and replay validation

Completed moves are autosaved to:

```text
~/.chain_reaction/autosave.json
~/.chain_reaction/replays/match-<timestamp>.json
```

`~` means your home folder on macOS, Windows or Linux. `--data-dir PATH` changes it.
Files are written atomically. A crash during an animation loses that pending move,
not the last completed autosave. Undo and a confirmed reset update the autosave.

A replay stores configuration and manual move coordinates, not executable code.
Loading reconstructs the state through the real engine and rejects illegal moves,
invalid configuration and oversized/over-budget data. Saved winner labels are not
trusted. You can load any exported replay with:

```sh
python run.py --replay /path/to/match.json
```

## Project structure

```text
run.py                       Application entry point and CLI
chain_reaction/
  engine.py                  Immutable states, legal moves, cascades, win/draw/abort
  session.py                 History, undo, atomic JSON saves and replay validation
  controller.py              Start/pause/step, timers and other UI interactions
  render.py                  Shared dark arena, board, orbs and controls
  window.py                  Pygame primary window + optional Tk fallback
  agents.py                  Future Agent protocol ONLY; no AI implementation
examples/
  cascade_example.json       Fixed replayed teaching position
tests/                       Engine, persistence, controller and renderer tests
tools/gui_smoke.py           Real-window mouse/keyboard/resize smoke test
```

## Future AI integration

The engine does not import Pygame or Pillow. The same rules are available without
a screen:

```python
from chain_reaction.engine import new_game, legal_moves, apply_move

state = new_game()
choices = legal_moves(state)
result = apply_move(state, choices[0])  # example supplied move; not an AI
next_state = result.state             # original state is unchanged
```

`agents.py` defines a future `choose_move(state, deadline) -> (row, col)` contract.
An AI scheduler/worker and each algorithm must still be implemented. Do not call
the empty protocol an implemented agent. The current application intentionally
supports only manual play; no AI mode is enabled or simulated.

## Testing

```sh
python -m unittest discover -s tests -v
python tools/gui_smoke.py
```

The second command opens a real Tk window and sends mouse events. On a Linux
headless testing host, use `xvfb-run -a python tools/gui_smoke.py`.

The delivered build passed **57 automated tests**, including **75 seeded random
input sequences** covering multiple board sizes. Random inputs exist only in the
tests, not as an agent in the game. Tests cover orb conservation, corner/edge/inner
thresholds, captures, elimination and skipping, winners, draw precedence, cascade
guards, undo, JSON validation, interaction state and text-boundary checks.

The desktop smoke test exercised Start, placement, Undo, Help, example loading,
Step, cancellation during a cascade, resize-aware clicks and reset/cancel.

**Environment verification:** Python 3.13.5, Pillow 12.3.0 and the Tk window adapter
were exercised here. Network restrictions prevented installing pygame-ce in the
build environment, so the Pygame window adapter has been syntax-checked but not
executed here. Windows/macOS launchers are supplied but were not executed on those
operating systems. Perform a short local smoke test before a classroom showcase.

### Fallback and troubleshooting

- `python run.py --backend tk` uses the same visuals and rules without Pygame;
  it needs Pillow and a working standard-library Tk installation.
- `python run.py --backend pygame` requires pygame-ce. Default `auto` prefers
  Pygame and falls back to Tk only when Pygame cannot be imported.
- Linux may need its distribution's Python Tk package for the fallback.
- Avoid running from inside the ZIP. Launchers must sit next to `run.py`.
- Smaller windows are uniformly scaled with letterboxing; input maps back to the
  board. Fullscreen is available. A window near 1366×873 gives readable controls.
- No sound, multiplayer networking, AI agents or model-training code is included.
- No fonts are distributed. Installed system fonts are used, with a Pillow fallback.

## Basis

Gameplay and UI follow the supplied Chain Reaction final deck and slide-by-slide
speech (especially slides 3–5). New engineering conveniences are clearly separated
above: default dimensions, board presets, undo, save/load, keyboard controls and
the opt-in draw cap. The Teeko presentation contributed only the earlier slide
sequence; none of its special moves or rules are used here.

Implementation documentation consulted:
- https://pyga.me/docs/
- https://pyga.me/docs/ref/display.html
- https://pyga.me/docs/ref/event.html
- https://pypi.org/project/pygame-ce/

This is an original implementation inspired by the provided visual reference,
not code copied from an existing Chain Reaction repository. The game requires no
bundled image asset or font file.
