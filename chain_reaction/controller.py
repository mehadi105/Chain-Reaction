"""UI-independent interaction state. Both window backends use this controller."""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import time

from .agents import AGENT_NAMES, agent_by_name
from .engine import Config, Event, InvalidMove, Status
from .session import Session, example_session

NAMES = ("Red", "Blue", "Green")
SPEEDS = ("Slow", "Normal", "Fast", "Instant")
DURATIONS = (0.55, 0.24, 0.08, 0.0)


class Controller:
    def __init__(self, config: Config | None = None, data_dir: Path | None = None):
        self.session = Session(config)
        self.data_dir = Path(data_dir).expanduser() if data_dir is not None else Path.home() / ".chain_reaction"
        self.storage_enabled = True
        self.started = False
        self.paused = False
        self.modal: str | None = None
        self.event: Event | None = None
        self.progress = 1.0
        self.speed = 1
        self.turn_seconds = 0.0
        self.age = 0.0
        self.message = "Press Start, then choose an empty cell."
        self.message_until = 8.0
        self.selected: tuple[int, int] | None = None
        self.focus_cell: tuple[int, int] | None = None
        self.show_counts = False
        self.example = False
        self.draft_board = (self.session.state.config.rows, self.session.state.config.cols)
        self.draft_limit = self.session.state.config.move_limit
        self.log_scroll = 0
        self.last_saved = ""
        self.seats = ["human", "human", "human"]
        self._agents = {name: agent_by_name(name) for name in AGENT_NAMES}

    @property
    def state(self):
        return self.session.state

    @property
    def busy(self) -> bool:
        return self.session.transaction is not None

    def notify(self, text: str, seconds: float = 4) -> None:
        self.message = text
        self.message_until = self.age + seconds

    def autosave(self) -> None:
        if self.storage_enabled and not self.busy:
            try:
                self.session.save(self.data_dir / "autosave.json")
            except (OSError, ValueError) as exc:
                self.notify(f"Autosave unavailable: {exc}", 6)

    def commit(self) -> None:
        record = self.session.commit()
        self.event = None
        self.progress = 1.0
        self.turn_seconds = 0.0
        self.log_scroll = 0
        result = record.result
        if result.state.status is Status.WON:
            self.notify(f"{NAMES[result.state.winner]} wins. All other colours have been eliminated.", 10)
        elif result.state.status is Status.DRAW:
            self.notify("Move-limit draw. More than one colour remains.", 10)
        elif result.state.status is Status.ABORTED:
            self.notify("Cascade safety stop. This is NOT a draw. Undo or reset the match.", 20)
        elif result.eliminated_now:
            gone = ", ".join(NAMES[p] for p in result.eliminated_now)
            self.notify(f"{gone} eliminated. Their turns will be skipped.", 5)
        elif result.topples:
            self.notify(f"{result.topples} explosions resolved; {result.captures} enemy cells captured.")
        self.autosave()

    def place(self, row: int, col: int) -> None:
        if self.modal:
            return
        if not self.started:
            self.notify("Press Start to begin the match.")
            return
        if self.paused:
            self.notify("The match is paused. Press Resume to place an orb.")
            return
        if self.busy:
            self.notify("A chain reaction is resolving. Pause + Step to inspect it.")
            return
        try:
            self.event = self.session.begin((row, col), self.turn_seconds)
            self.selected = (row, col)
            self.focus_cell = None
            self.progress = 0.0
        except InvalidMove as exc:
            self.notify(str(exc))

    def update(self, dt: float) -> None:
        self.age += max(0, dt)
        if self.modal or not self.started or self.paused:
            return
        if not self.busy:
            if self.state.status is Status.PLAYING:
                self.turn_seconds += max(0, dt)
                self._play_agent_turn()
            return
        duration = DURATIONS[self.speed]
        if duration == 0:
            # Bounded work per frame keeps quit/pause events responsive.
            for _ in range(128):
                tx = self.session.transaction
                if tx is None:
                    return
                if tx.done:
                    self.commit()
                    return
                self.event = tx.advance()
            self.progress = 1.0
            return
        self.progress += min(dt, 0.1) / duration
        if self.progress >= 1:
            tx = self.session.transaction
            assert tx is not None
            if tx.done:
                self.commit()
            else:
                self.event = tx.advance()
                self.progress = 0
                if self.event is None and tx.done:
                    self.commit()

    def assign_agent(self, index: int) -> None:
        if self.busy:
            self.notify("Wait until the chain reaction finishes before changing a seat.")
            return
        if not 0 <= index < len(AGENT_NAMES):
            return
        name = AGENT_NAMES[index]
        player = self.state.current_player
        self._set_seat(player, "human" if self.seats[player] == name else name)

    def toggle_seat(self, player: int) -> None:
        """Cycle one seat: human, then each agent, then human again."""
        if self.busy:
            self.notify("Wait until the chain reaction finishes before changing a seat.")
            return
        if not 0 <= player < len(self.seats):
            return
        order = ("human",) + AGENT_NAMES
        try:
            nxt = order[(order.index(self.seats[player]) + 1) % len(order)]
        except ValueError:
            nxt = "human"
        self._set_seat(player, nxt)

    def _set_seat(self, player: int, name: str) -> None:
        self.seats[player] = name
        if name == "human":
            self.notify(f"{NAMES[player]} is human again.")
        else:
            self.notify(f"{NAMES[player]} will play as {name}.")

    def _play_agent_turn(self) -> None:
        player = self.state.current_player
        name = self.seats[player] if player < len(self.seats) else "human"
        agent = self._agents.get(name)
        if agent is None or self.state.status is not Status.PLAYING:
            return
        try:
            move = agent.choose_move(self.state, time.monotonic() + 0.22)
            self.place(*move)
        except (InvalidMove, ValueError) as exc:
            self.seats[player] = "human"
            self.notify(f"{name} could not move ({exc}). {NAMES[player]} is human again.", 6)

    def step(self) -> None:
        if not self.busy:
            self.notify("Step inspects explosions. Place an orb that starts a cascade first.")
            return
        self.paused = True
        tx = self.session.transaction
        assert tx is not None
        if tx.done:
            self.commit()
        else:
            self.event = tx.advance()
            self.progress = 1.0
            if self.event is None and tx.done:
                self.commit()

    def open_new(self) -> None:
        self.draft_board = (self.state.config.rows, self.state.config.cols)
        self.draft_limit = self.state.config.move_limit
        self.modal = "new"

    def reset(self, config: Config | None = None, *, start: bool = False) -> None:
        self.session = Session(config or self.state.config)
        self.started = start
        self.paused = False
        self.event = None
        self.progress = 1
        self.turn_seconds = 0
        self.selected = self.focus_cell = None
        self.modal = None
        self.example = False
        self.log_scroll = 0
        self.notify("New board. Red moves first.")
        self.autosave()

    def action(self, action: str) -> None:
        if action == "close":
            self.modal = None
        elif action == "startpause":
            if self.state.status is not Status.PLAYING and not self.busy:
                self.open_new()
            elif not self.started:
                self.started = True
                self.notify("Red to move. Choose an empty cell or one you own.")
            else:
                self.paused = not self.paused
                self.notify("Paused. Step advances one explosion." if self.paused else "Match resumed.")
        elif action == "step":
            self.step()
        elif action == "undo":
            if self.session.undo():
                self.event = None
                self.progress = 1
                self.turn_seconds = 0
                self.selected = self.session.history[-1].result.move if self.session.history else None
                self.notify("Last move undone. The previous turn is restored.")
                self.log_scroll = 0
                self.autosave()
        elif action == "new":
            self.open_new()
        elif action == "reset":
            self.modal = "reset"
        elif action == "confirm_reset":
            self.reset(start=True)
        elif action == "confirm_new":
            r, c = self.draft_board
            self.reset(Config(rows=r, cols=c, move_limit=self.draft_limit), start=True)
        elif action.startswith("board:"):
            self.draft_board = tuple(map(int, action.split(":")[1:]))
        elif action.startswith("limit:"):
            self.draft_limit = int(action.split(":")[1]) or None
        elif action == "help":
            self.modal = "help"
        elif action == "load":
            self.modal = "load"
        elif action == "confirm_load":
            try:
                loaded = Session.load(self.data_dir / "autosave.json")
                self.load_session(loaded)
                self.notify("Autosave loaded; move history has been validated.")
            except (OSError, ValueError) as exc:
                self.modal = None
                self.notify(f"Cannot load: {exc}", 8)
        elif action == "save":
            if self.busy:
                self.notify("Finish or undo the cascade before saving.")
            else:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                path = self.data_dir / "replays" / f"match-{stamp}.json"
                try:
                    self.session.save(path)
                    self.last_saved = str(path)
                    self.notify("Replay saved in ~/.chain_reaction/replays/", 6)
                except (OSError, ValueError) as exc:
                    self.notify(f"Save failed: {exc}", 8)
        elif action == "example":
            self.load_session(example_session())
            self.example = True
            self.notify("Example position: Red can trigger a cascade at A1. These are replayed manual moves.", 12)
        elif action == "speed":
            self.speed = (self.speed + 1) % len(SPEEDS)
        elif action == "counts":
            self.show_counts = not self.show_counts
        elif action.startswith("agent:"):
            self.assign_agent(int(action.split(":", 1)[1]))
        elif action.startswith("seat:"):
            self.toggle_seat(int(action.split(":", 1)[1]))

    def load_session(self, session: Session) -> None:
        self.session = session
        self.started = True
        self.paused = False
        self.event = None
        self.progress = 1
        self.turn_seconds = 0
        self.selected = session.history[-1].result.move if session.history else None
        self.focus_cell = None
        self.modal = None
        self.example = False
        self.log_scroll = 0

    def key(self, key: str) -> None:
        if key == "escape":
            if self.modal:
                self.modal = None
            elif self.started and self.state.status is Status.PLAYING:
                self.paused = True
            return
        if self.modal:
            if key == "enter":
                mapping = {"new": "confirm_new", "reset": "confirm_reset", "load": "confirm_load"}
                if self.modal in mapping:
                    self.action(mapping[self.modal])
            return
        actions = {"space": "startpause", "p": "startpause", "n": "new", "r": "reset",
                   "u": "undo", "s": "save", "l": "load", "h": "help", "f1": "help",
                   ".": "step", "f": "speed", "c": "counts"}
        if key in actions:
            self.action(actions[key])
        elif key in ("up", "right", "down", "left"):
            r, c = self.focus_cell or (0, 0)
            dr, dc = {"up": (-1, 0), "right": (0, 1), "down": (1, 0), "left": (0, -1)}[key]
            self.focus_cell = (max(0, min(self.state.config.rows - 1, r + dr)),
                               max(0, min(self.state.config.cols - 1, c + dc)))
        elif key == "enter":
            if not self.started:
                self.action("startpause")
            elif self.focus_cell is not None:
                self.place(*self.focus_cell)
