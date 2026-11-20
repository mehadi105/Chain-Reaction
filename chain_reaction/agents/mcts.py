"""Stub for the Monte Carlo agent. Replace this file with the real search."""
from ..engine import legal_moves


class MCTSAgent:
    name = "MCTS"

    def __init__(self, seed=None, rollout_depth=6, iterations=10000):
        self.seed = seed
        self.rollout_depth = rollout_depth
        self.iterations = iterations

    def choose_move(self, state, deadline):
        moves = legal_moves(state)
        if not moves:
            raise ValueError("No legal move")
        return moves[0]
