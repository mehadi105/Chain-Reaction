"""Future extension contract only. NO AI algorithms are implemented in this build."""
from typing import Protocol
from .engine import State, Move


class Agent(Protocol):
    def choose_move(self, state: State, deadline: float) -> Move:
        """Return one legal move before a monotonic deadline.

        Future agents should use engine.legal_moves and engine.apply_move on the
        immutable state. Never mutate the real match or drive the renderer.
        The GUI does not yet schedule agents. A worker/scheduler will be needed.
        """
        ...


PLANNED_AGENTS = ("Minimax + alpha-beta", "MCTS", "CP-SAT planner")
