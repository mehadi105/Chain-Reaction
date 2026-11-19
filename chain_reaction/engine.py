"""Pure-Python rules. No rendering, clocks, random choices, or AI.

One placement is one move. A cascade is processed in FIFO order, with neighbours
ordered up, right, down, left. Each explosion is atomic and conserves orb count.
A win may terminate a cascade as soon as no other colour remains (after entry).
A repeated cascade state or a safety budget exhaustion is ABORTED, never a draw.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Iterator

Move = tuple[int, int]


class Status(str, Enum):
    PLAYING = "playing"
    WON = "won"
    DRAW = "draw"
    ABORTED = "aborted"


class InvalidMove(ValueError):
    """Invalid input leaves the original immutable state unchanged."""


@dataclass(frozen=True, slots=True)
class Config:
    rows: int = 9
    cols: int = 6
    players: int = 3
    move_limit: int | None = None
    max_topples: int = 10000

    def __post_init__(self) -> None:
        for name in ("rows", "cols", "players", "max_topples"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer")
        if not (3 <= self.rows <= 16 and 3 <= self.cols <= 12):
            raise ValueError("Board dimensions must be 3..16 rows and 3..12 columns")
        if self.players != 3:
            raise ValueError("This project uses exactly three players")
        if not 1 <= self.max_topples <= 100000:
            raise ValueError("max_topples must be in 1..100000")
        if self.move_limit is not None:
            if type(self.move_limit) is not int or not 3 <= self.move_limit <= 10000:
                raise ValueError("Move limit must be None or an integer in 3..10000")


@dataclass(frozen=True, slots=True)
class Cell:
    owner: int = -1
    count: int = 0


EMPTY = Cell()


@dataclass(frozen=True, slots=True)
class State:
    config: Config
    board: tuple[Cell, ...]
    current_player: int = 0
    moves_taken: tuple[int, ...] = (0, 0, 0)
    eliminated: frozenset[int] = frozenset()
    move_number: int = 0
    status: Status = Status.PLAYING
    winner: int | None = None
    reason: str = ""

    def cell(self, row: int, col: int) -> Cell:
        if not 0 <= row < self.config.rows or not 0 <= col < self.config.cols:
            raise IndexError("Cell is outside the board")
        return self.board[row * self.config.cols + col]

    @property
    def everyone_entered(self) -> bool:
        return all(n > 0 for n in self.moves_taken)

    def counts(self) -> tuple[tuple[int, int], ...]:
        """One (orbs, controlled_cells) pair per player."""
        orbs = [0] * self.config.players
        cells = [0] * self.config.players
        for cell in self.board:
            if cell.count:
                orbs[cell.owner] += cell.count
                cells[cell.owner] += 1
        return tuple(zip(orbs, cells))


def new_game(config: Config | None = None) -> State:
    c = config or Config()
    return State(c, (EMPTY,) * (c.rows * c.cols))


@lru_cache(maxsize=48)
def neighbour_table(rows: int, cols: int) -> tuple[tuple[int, ...], ...]:
    out = []
    for r in range(rows):
        for c in range(cols):
            ns = []
            for dr, dc in ((-1, 0), (0, 1), (1, 0), (0, -1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < rows and 0 <= cc < cols:
                    ns.append(rr * cols + cc)
            out.append(tuple(ns))
    return tuple(out)


def critical_mass(config: Config, row: int, col: int) -> int:
    if not 0 <= row < config.rows or not 0 <= col < config.cols:
        raise IndexError("Cell is outside the board")
    return len(neighbour_table(config.rows, config.cols)[row * config.cols + col])


def legal_moves(state: State) -> tuple[Move, ...]:
    if state.status is not Status.PLAYING:
        return ()
    return tuple(divmod(i, state.config.cols) for i, c in enumerate(state.board)
                 if c.owner in (-1, state.current_player))


def check_move(state: State, move: Move) -> None:
    if state.status is not Status.PLAYING:
        raise InvalidMove("This match is over. Start a new match or undo a move.")
    if not isinstance(move, (tuple, list)) or len(move) != 2 or any(type(x) is not int for x in move):
        raise InvalidMove("A move must be an integer (row, column) pair")
    row, col = move
    if not (0 <= row < state.config.rows and 0 <= col < state.config.cols):
        raise InvalidMove("Choose a cell inside the board.")
    if state.cell(row, col).owner not in (-1, state.current_player):
        raise InvalidMove("That cell belongs to another player. Capture it through an explosion.")


@dataclass(frozen=True, slots=True)
class Event:
    kind: str
    source: Move
    targets: tuple[Move, ...]
    player: int
    before: tuple[Cell, ...]
    after: tuple[Cell, ...]
    captures: int = 0


@dataclass(frozen=True, slots=True)
class Result:
    state: State
    move: Move
    player: int
    topples: int
    captures: int
    eliminated_now: tuple[int, ...]


class MoveTransaction:
    """Incremental resolver: advances one explosion, never blocks on a full cascade.

    `base` is never mutated. Discarding this object cancels an unfinished move.
    `placement` is the initial visual event. Repeated `advance()` calls supply
    subsequent atomic explosions. When `done`, `result` is the turn boundary or
    an explicit terminal/aborted state.
    """
    def __init__(self, state: State, move: Move):
        check_move(state, move)
        self.base = state
        self.move = tuple(move)
        self.player = state.current_player
        self.config = state.config
        self._board = list(state.board)
        self._neighbours = neighbour_table(self.config.rows, self.config.cols)
        self._queue: deque[int] = deque()
        self._queued: set[int] = set()
        self._seen: set[tuple] = set()
        self.topples = 0
        self.captures = 0
        self.result: Result | None = None
        self._taken = list(state.moves_taken)
        self._taken[self.player] += 1
        idx = move[0] * self.config.cols + move[1]
        old = self._board[idx]
        self._board[idx] = Cell(self.player, old.count + 1)
        self.placement = Event("place", self.move, (), self.player, state.board, tuple(self._board))
        self._enqueue(idx)
        self._check_complete()
        if not self.done:
            self._seen.add(self._key())

    @property
    def done(self) -> bool:
        return self.result is not None

    @property
    def board(self) -> tuple[Cell, ...]:
        return tuple(self._board)

    def _enqueue(self, idx: int) -> None:
        if self._board[idx].count >= len(self._neighbours[idx]) and idx not in self._queued:
            self._queue.append(idx)
            self._queued.add(idx)

    def _key(self) -> tuple:
        # Queue order and ownership matter for deterministic cycle detection.
        return (tuple(self._board), tuple(self._queue))

    def _finish(self, status: Status, winner: int | None = None, reason: str = "") -> None:
        present = {c.owner for c in self._board if c.count}
        eliminated = (frozenset(set(range(self.config.players)) - present)
                      if all(self._taken) else self.base.eliminated)
        next_player = self.player
        if status is Status.PLAYING:
            for _ in range(self.config.players):
                next_player = (next_player + 1) % self.config.players
                if next_player not in eliminated:
                    break
        final = State(self.config, tuple(self._board), next_player, tuple(self._taken), eliminated,
                      self.base.move_number + 1, status, winner, reason)
        self.result = Result(final, self.move, self.player, self.topples, self.captures,
                             tuple(sorted(eliminated - self.base.eliminated)))

    def _check_complete(self) -> None:
        present = {c.owner for c in self._board if c.count}
        if all(self._taken) and len(present) == 1:
            # The winner is already certain: stop even if own orbs can still topple.
            self._finish(Status.WON, next(iter(present)), "last_colour")
        elif not self._queue:
            limit = self.config.move_limit
            if limit is not None and self.base.move_number + 1 >= limit:
                self._finish(Status.DRAW, reason="move_limit")
            else:
                self._finish(Status.PLAYING)

    def advance(self) -> Event | None:
        if self.done:
            return None
        if self.topples >= self.config.max_topples:
            self._finish(Status.ABORTED, reason="cascade_budget")
            return None
        idx = self._queue.popleft()
        self._queued.remove(idx)
        before = tuple(self._board)
        targets = self._neighbours[idx]
        remaining = self._board[idx].count - len(targets)
        assert remaining >= 0, "Only unstable cells are queued"
        self._board[idx] = Cell(self.player, remaining) if remaining else EMPTY
        captured = 0
        for target in targets:
            old = self._board[target]
            captured += int(old.count > 0 and old.owner != self.player)
            self._board[target] = Cell(self.player, old.count + 1)
            self._enqueue(target)
        self._enqueue(idx)
        self.topples += 1
        self.captures += captured
        event = Event("explode", divmod(idx, self.config.cols),
                      tuple(divmod(t, self.config.cols) for t in targets),
                      self.player, before, tuple(self._board), captured)
        self._check_complete()
        if not self.done:
            key = self._key()
            if key in self._seen:
                self._finish(Status.ABORTED, reason="cascade_cycle")
            else:
                self._seen.add(key)
        return event


def apply_move(state: State, move: Move) -> Result:
    """Headless deterministic move resolution, suitable for future agent simulation."""
    tx = MoveTransaction(state, move)
    while not tx.done:
        tx.advance()
    assert tx.result is not None
    return tx.result


def validate_state(state: State, *, require_stable: bool = True) -> None:
    """Defensive checks for tests and custom future integrations."""
    cfg = state.config
    if len(state.board) != cfg.rows * cfg.cols:
        raise ValueError("Wrong board size")
    if not 0 <= state.current_player < cfg.players:
        raise ValueError("Invalid current player")
    if len(state.moves_taken) != cfg.players or any(type(n) is not int or n < 0 for n in state.moves_taken):
        raise ValueError("Invalid player turn counts")
    if sum(state.moves_taken) != state.move_number:
        raise ValueError("Move number and turn counts disagree")
    for i, cell in enumerate(state.board):
        if type(cell.count) is not int or cell.count < 0:
            raise ValueError("Invalid orb count")
        if cell.count == 0 and cell.owner != -1:
            raise ValueError("Empty cell must have owner -1")
        if cell.count and not 0 <= cell.owner < cfg.players:
            raise ValueError("Invalid cell owner")
        if require_stable and state.status is Status.PLAYING and cell.count >= len(neighbour_table(cfg.rows, cfg.cols)[i]):
            raise ValueError("A playable turn-boundary board must be stable")
    if state.status is Status.PLAYING and state.current_player in state.eliminated:
        raise ValueError("Eliminated player cannot act")
