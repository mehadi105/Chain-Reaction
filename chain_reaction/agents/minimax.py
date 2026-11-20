"""Stub for the minimax agent. Replace this file with the real search."""
from ..engine import legal_moves


class MinimaxAgent:
    name = "Minimax + alpha-beta"

    def __init__(self, depth=6):
        self.depth = depth

    def choose_move(self, state, deadline):
        moves = legal_moves(state)
        if not moves:
            raise ValueError("No legal move")
        return moves[0]
