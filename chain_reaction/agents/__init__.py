"""Agent contract and the three lab-style players.

minimax.py, mcts.py and cpsat.py each follow the functions from the lab
(actions/result/max-min, MCTSNode/ucb1, and backtracking with forward checking).
`choose_move` is the small adapter the match uses to ask for one legal cell.
"""
from __future__ import annotations
from typing import Protocol

from ..engine import Move, State

__all__ = (
    "Agent",
    "AGENT_NAMES",
    "MinimaxAgent",
    "MCTSAgent",
    "CPSATAgent",
    "agent_by_name",
)


class Agent(Protocol):
    name: str

    def choose_move(self, state: State, deadline: float) -> Move:
        """Return one legal move before `deadline` (`time.monotonic()` seconds)."""


from .minimax import MinimaxAgent
from .mcts import MCTSAgent
from .cpsat import CPSATAgent

AGENT_NAMES = (MinimaxAgent.name, MCTSAgent.name, CPSATAgent.name)
_FACTORIES = {
    MinimaxAgent.name: MinimaxAgent,
    MCTSAgent.name: MCTSAgent,
    CPSATAgent.name: CPSATAgent,
}


def agent_by_name(name: str) -> Agent:
    try:
        return _FACTORIES[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown agent: {name}") from exc
