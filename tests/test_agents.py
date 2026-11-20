import time
import unittest

from chain_reaction.agents import CPSATAgent, MCTSAgent, MinimaxAgent, agent_by_name
from chain_reaction.controller import Controller
from chain_reaction.engine import Cell, Config, EMPTY, State, Status, legal_moves, new_game


def winning_corner():
    """Red explodes the center, which is not the first legal cell."""
    board = [EMPTY] * 9
    board[4] = Cell(0, 3)
    board[1] = Cell(1, 1)
    board[3] = Cell(2, 1)
    board[5] = Cell(1, 1)
    board[7] = Cell(2, 1)
    return State(Config(rows=3, cols=3), tuple(board), 0, (1, 1, 1), frozenset(), 3, Status.PLAYING)


class AgentTests(unittest.TestCase):
    def test_each_agent_returns_a_legal_move_without_changing_state(self):
        state = new_game(Config(rows=5, cols=5))
        for agent in (MinimaxAgent(), MCTSAgent(seed=1), CPSATAgent()):
            before = state
            deadline = time.monotonic() + 0.2
            move = agent.choose_move(state, deadline)
            self.assertIn(move, legal_moves(state))
            self.assertEqual(state, before)
            self.assertLess(time.monotonic(), deadline + 0.35)

    def test_expired_deadline_still_returns_a_legal_move(self):
        state = new_game()
        for agent in (MinimaxAgent(), MCTSAgent(seed=2), CPSATAgent()):
            move = agent.choose_move(state, time.monotonic() - 1)
            self.assertIn(move, legal_moves(state))

    def test_minimax_and_cpsat_take_an_immediate_win(self):
        state = winning_corner()
        deadline = time.monotonic() + 1.0
        self.assertEqual(MinimaxAgent(depth=2).choose_move(state, deadline), (1, 1))
        self.assertEqual(CPSATAgent().choose_move(state, deadline), (1, 1))

    def test_mcts_prefers_the_winning_cell(self):
        state = winning_corner()
        move = MCTSAgent(seed=0, rollout_depth=4).choose_move(state, time.monotonic() + 0.4)
        self.assertEqual(move, (1, 1))

    def test_unknown_agent_name_is_rejected(self):
        with self.assertRaises(ValueError):
            agent_by_name("random bot")

    def test_seated_agent_plays_a_move(self):
        match = Controller(Config(rows=3, cols=3))
        match.storage_enabled = False
        match.seats[0] = "Minimax + alpha-beta"
        match.action("startpause")
        match.update(0.01)
        self.assertTrue(match.busy)
        self.assertEqual(match.session.transaction.player, 0)

    def test_each_player_card_toggles_human_and_ai(self):
        match = Controller()
        match.storage_enabled = False
        match.action("seat:1")
        self.assertEqual(match.seats[1], "Minimax + alpha-beta")
        match.action("seat:1")
        self.assertEqual(match.seats[1], "MCTS")
        match.action("seat:1")
        self.assertEqual(match.seats[1], "CP-SAT planner")
        match.action("seat:1")
        self.assertEqual(match.seats, ["human", "human", "human"])
        self.assertEqual(match.seats[0], "human")

    def test_clicking_an_agent_seats_and_clears_the_mover(self):
        match = Controller()
        match.storage_enabled = False
        match.action("agent:1")
        self.assertEqual(match.seats[0], "MCTS")
        match.action("agent:1")
        self.assertEqual(match.seats, ["human", "human", "human"])


if __name__ == "__main__":
    unittest.main()
