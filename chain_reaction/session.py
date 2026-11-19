"""Local match history, undo and validated, portable JSON replays."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile
import time

from .engine import Config, Event, Move, MoveTransaction, Result, State, Status, new_game


@dataclass(frozen=True, slots=True)
class Record:
    before: State
    result: Result
    elapsed: float


class Session:
    def __init__(self, config: Config | None = None):
        self.state = new_game(config)
        self.history: list[Record] = []
        self.transaction: MoveTransaction | None = None
        self.pending_elapsed = 0.0

    def begin(self, move: Move, elapsed: float = 0) -> Event:
        if self.transaction is not None:
            raise ValueError("Finish or cancel the current cascade first")
        tx = MoveTransaction(self.state, move)
        self.transaction = tx
        self.pending_elapsed = max(0.0, elapsed)
        return tx.placement

    def commit(self) -> Record:
        tx = self.transaction
        if tx is None or not tx.done or tx.result is None:
            raise ValueError("Cannot commit an unfinished move")
        record = Record(self.state, tx.result, self.pending_elapsed)
        self.history.append(record)
        self.state = tx.result.state
        self.transaction = None
        return record

    def play(self, move: Move, elapsed: float = 0) -> Record:
        """Headless path for replay and testing; never chooses a move itself."""
        self.begin(move, elapsed)
        assert self.transaction is not None
        while not self.transaction.done:
            self.transaction.advance()
        return self.commit()

    def undo(self) -> bool:
        if self.transaction is not None:
            self.transaction = None
            return True
        if not self.history:
            return False
        self.state = self.history.pop().before
        return True

    @property
    def board(self):
        return self.transaction.board if self.transaction else self.state.board

    def to_document(self) -> dict:
        if self.transaction is not None:
            raise ValueError("Finish or undo the cascade before saving")
        return {
            "format": "chain-reaction-replay",
            "version": 1,
            "rules": "fifo-urdl-v1",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "config": asdict(self.state.config),
            "moves": [
                {"row": r.result.move[0], "col": r.result.move[1], "turn_seconds": round(r.elapsed, 3)}
                for r in self.history
            ],
            "result": {"status": self.state.status.value, "winner": self.state.winner,
                       "reason": self.state.reason},
        }

    def save(self, path: Path) -> None:
        document = self.to_document()
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=".chain-reaction-", delete=False) as f:
                tmp = Path(f.name)
                json.dump(document, f, indent=2, allow_nan=False)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if tmp is not None and tmp.exists():
                tmp.unlink()

    @classmethod
    def load(cls, path: Path) -> Session:
        path = Path(path).expanduser()
        if path.stat().st_size > 2_000_000:
            raise ValueError("Replay file is too large (maximum 2 MB)")
        return cls.from_document(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def from_document(cls, document: dict) -> Session:
        if not isinstance(document, dict) or document.get("format") != "chain-reaction-replay":
            raise ValueError("Not a Chain Reaction replay")
        if document.get("version") != 1 or document.get("rules") != "fifo-urdl-v1":
            raise ValueError("Unsupported replay version or rules")
        cfg = document.get("config")
        if not isinstance(cfg, dict):
            raise ValueError("Missing board configuration")
        try:
            session = cls(Config(**cfg))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid configuration: {exc}") from exc
        moves = document.get("moves")
        if not isinstance(moves, list) or len(moves) > 2000:
            raise ValueError("Replay must contain at most 2000 moves")
        deadline = time.monotonic() + 8
        total_topples = 0
        for i, entry in enumerate(moves):
            if not isinstance(entry, dict):
                raise ValueError(f"Invalid move entry {i + 1}")
            elapsed = entry.get("turn_seconds", 0)
            if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or not 0 <= elapsed <= 1e8:
                raise ValueError("Invalid turn duration")
            try:
                session.begin((entry.get("row"), entry.get("col")), elapsed)
                tx = session.transaction
                assert tx is not None
                while not tx.done:
                    tx.advance()
                    total_topples += 1
                    if total_topples > 50000 or time.monotonic() > deadline:
                        raise ValueError("Replay exceeds safe processing budget")
                session.commit()
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid replay move {i + 1}: {exc}") from exc
        # Saved boards / winners are never trusted; the state is replayed from empty.
        return session


def example_session() -> Session:
    """A fixed sequence of legal, manually specified moves, not a playing agent.

    All 36 placements are replayed through the real engine. Red is next. A1 (top
    left) starts a cascade. This is a teaching position, not a match result.
    """
    red = [(0, 0), (1, 0), (1, 0), (4, 1), (4, 1), (4, 1),
           (6, 2), (6, 2), (4, 4), (4, 4), (7, 0), (7, 0)]
    blue = [(0, 1), (0, 1), (2, 2), (2, 2), (2, 2), (4, 2),
            (4, 2), (4, 2), (7, 3), (7, 3), (7, 3), (8, 0)]
    green = [(1, 1), (1, 1), (1, 1), (3, 0), (3, 0), (3, 3),
             (3, 3), (3, 3), (6, 1), (6, 1), (6, 1), (8, 5)]
    session = Session()
    for triplet in zip(red, blue, green):
        for move in triplet:
            session.play(move)
    return session
