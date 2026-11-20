"""Stub for the forward-checking agent. Replace this file with the real search."""
from ..engine import legal_moves


class CPSATAgent:
    name = "CP-SAT planner"

    def __init__(self, horizon=4):
        self.horizon = horizon

    def choose_move(self, state, deadline):
        moves = legal_moves(state)
        if not moves:
            raise ValueError("No legal move")
        return moves[0]
