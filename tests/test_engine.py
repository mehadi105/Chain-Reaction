import random
import unittest
from dataclasses import FrozenInstanceError, replace
from chain_reaction.engine import (
    Cell, EMPTY, Config, State, Status, InvalidMove, MoveTransaction,
    apply_move, critical_mass, legal_moves, new_game, validate_state,
)
from chain_reaction.session import Session, example_session


def fixture(cells, config=None, current=0, taken=(1,1,1)):
    config=config or Config(rows=3,cols=3)
    board=[EMPTY]*(config.rows*config.cols)
    for (r,c),(p,n) in cells.items():
        board[r*config.cols+c]=Cell(p,n)
    return State(config,tuple(board),current,taken,move_number=sum(taken))


class EngineTests(unittest.TestCase):
    def test_initial_state(self):
        s=new_game(); validate_state(s)
        self.assertEqual(len(s.board),54)
        self.assertEqual(len(legal_moves(s)),54)
        self.assertEqual(s.counts(),((0,0),(0,0),(0,0)))

    def test_configuration_validation(self):
        for args in ({'rows':2},{'cols':13},{'players':2},{'move_limit':2},
                     {'rows':True},{'max_topples':0},{'move_limit':3.0}):
            with self.subTest(args=args),self.assertRaises(ValueError): Config(**args)

    def test_thresholds(self):
        c=Config()
        self.assertEqual(critical_mass(c,0,0),2)
        self.assertEqual(critical_mass(c,0,2),3)
        self.assertEqual(critical_mass(c,2,2),4)
        self.assertEqual(critical_mass(c,8,5),2)

    def test_immutable_simulation(self):
        s=new_game(); out=apply_move(s,(0,0))
        self.assertEqual(s.cell(0,0),EMPTY)
        self.assertEqual(out.state.cell(0,0),Cell(0,1))
        with self.assertRaises(FrozenInstanceError): s.current_player=2

    def test_no_diagonal_transfer(self):
        s=fixture({(0,0):(0,1),(2,0):(1,1),(2,2):(2,1)})
        r=apply_move(s,(0,0))
        self.assertEqual(r.state.cell(0,1),Cell(0,1))
        self.assertEqual(r.state.cell(1,0),Cell(0,1))
        self.assertEqual(r.state.cell(1,1),EMPTY)
        self.assertEqual(r.topples,1)

    def test_edge_explosion(self):
        s=fixture({(0,1):(0,2),(2,0):(1,1),(2,2):(2,1)})
        r=apply_move(s,(0,1)); self.assertEqual(r.topples,1)
        for rc in ((0,0),(0,2),(1,1)):
            self.assertEqual(r.state.cell(*rc),Cell(0,1))
        self.assertEqual(r.state.cell(0,1),EMPTY)

    def test_interior_explosion(self):
        s=fixture({(1,1):(0,3),(0,0):(1,1),(2,2):(2,1)})
        r=apply_move(s,(1,1)); self.assertEqual(r.topples,1)
        for rc in ((0,1),(1,2),(2,1),(1,0)):
            self.assertEqual(r.state.cell(*rc),Cell(0,1))

    def test_capture_recolours_all_orbs(self):
        s=fixture({(0,0):(0,1),(0,1):(1,1),(2,2):(2,1)})
        r=apply_move(s,(0,0))
        self.assertEqual(r.state.cell(0,1),Cell(0,2))
        self.assertEqual(r.captures,1)

    def test_chain_example_two_explosions(self):
        s=fixture({(0,0):(0,1),(0,1):(1,2),(1,1):(2,1)})
        r=apply_move(s,(0,0))
        self.assertEqual(r.topples,2)
        self.assertEqual(r.state.status,Status.WON)
        self.assertEqual(r.state.winner,0)
        self.assertEqual(sum(c.count for c in r.state.board),5)
        self.assertEqual(r.state.cell(1,1),Cell(0,2))
        self.assertEqual(r.state.cell(0,0),Cell(0,1))

    def test_cascade_has_deterministic_fifo_targets(self):
        s=fixture({(1,1):(0,3),(0,0):(1,1),(2,2):(2,1)})
        tx=MoveTransaction(s,(1,1)); e=tx.advance()
        self.assertEqual(e.targets,((0,1),(1,2),(2,1),(1,0)))
        self.assertTrue(tx.done)

    def test_residual_orbs_not_erased(self):
        # The teaching position sends multiple arrivals into already-full cells.
        ss=example_session(); old=sum(c.count for c in ss.state.board)
        tx=MoveTransaction(ss.state,(0,0))
        while not tx.done:
            ev=tx.advance()
            if ev: self.assertEqual(sum(c.count for c in ev.after),old+1)
        self.assertEqual(sum(c.count for c in tx.result.state.board),old+1)

    def test_first_turn_protection(self):
        s=apply_move(new_game(),(0,0)).state
        self.assertEqual(s.status,Status.PLAYING)
        self.assertEqual(s.eliminated,frozenset())
        self.assertEqual(s.current_player,1)
        s=apply_move(s,(0,1)).state
        self.assertEqual(s.current_player,2)
        self.assertEqual(s.eliminated,frozenset())

    def test_elimination_skip(self):
        s=fixture({(0,0):(0,1),(0,1):(1,1),(2,2):(2,1)})
        r=apply_move(s,(0,0))
        self.assertEqual(r.state.eliminated,frozenset({1}))
        self.assertEqual(r.state.current_player,2)
        s2=apply_move(r.state,(2,1)).state
        self.assertEqual(s2.current_player,0)

    def test_elimination_waits_for_all_initial_turns(self):
        s=fixture({(0,0):(0,1),(0,1):(1,1)},taken=(1,1,0))
        r=apply_move(s,(0,0))
        self.assertEqual(r.state.status,Status.PLAYING)
        self.assertEqual(r.state.eliminated,frozenset())

    def test_winner_does_not_require_full_board(self):
        s=fixture({(0,0):(0,1),(0,1):(1,1),(1,0):(2,1)})
        out=apply_move(s,(0,0))
        self.assertEqual(out.state.status,Status.WON)
        self.assertTrue(any(c.count==0 for c in out.state.board))

    def test_illegal_enemy_move_does_not_advance(self):
        s=apply_move(new_game(),(0,0)).state
        with self.assertRaises(InvalidMove): apply_move(s,(0,0))
        self.assertEqual(s.move_number,1)

    def test_invalid_coordinates(self):
        for move in ((-1,0),(100,0),(1.1,0),(True,0),(0,),"A1",(0,None)):
            with self.subTest(move=move),self.assertRaises(InvalidMove):
                apply_move(new_game(),move)

    def test_reject_after_win(self):
        s=fixture({(0,0):(0,1),(0,1):(1,1),(1,0):(2,1)})
        s=apply_move(s,(0,0)).state
        self.assertFalse(legal_moves(s))
        with self.assertRaises(InvalidMove): apply_move(s,(2,2))

    def test_move_limit_draw_is_optional(self):
        ss=Session(Config(move_limit=3))
        for rc in ((0,0),(0,2),(8,5)): ss.play(rc)
        self.assertEqual(ss.state.status,Status.DRAW)
        self.assertEqual(ss.state.reason,"move_limit")
        self.assertIsNone(ss.state.winner)

    def test_default_no_draw_limit(self):
        ss=Session()
        for rc in ((0,0),(0,2),(8,5)): ss.play(rc)
        self.assertEqual(ss.state.status,Status.PLAYING)

    def test_win_takes_precedence_over_limit(self):
        c=Config(rows=3,cols=3,move_limit=4)
        s=fixture({(0,0):(0,1),(0,1):(1,1),(1,0):(2,1)},config=c)
        self.assertEqual(apply_move(s,(0,0)).state.status,Status.WON)

    def test_draw_checked_after_cascade(self):
        ss=example_session()
        s=replace(ss.state,config=replace(ss.state.config,move_limit=37))
        r=apply_move(s,(0,0))
        self.assertEqual(r.state.status,Status.DRAW)
        self.assertEqual(r.topples,5)
        for idx,c in enumerate(r.state.board):
            self.assertLess(c.count,critical_mass(s.config,*divmod(idx,s.config.cols)))

    def test_safety_budget_is_abort_not_draw(self):
        ss=example_session()
        s=replace(ss.state,config=replace(ss.state.config,max_topples=1))
        r=apply_move(s,(0,0))
        self.assertEqual(r.state.status,Status.ABORTED)
        self.assertEqual(r.state.reason,"cascade_budget")

    def test_repeated_unsettled_state_is_abort(self):
        c=Config(rows=3,cols=3,max_topples=1000)
        # Synthetic guard test: entry protection plus an overfull conserved board.
        cells={(r,col):((r+col)%3,critical_mass(c,r,col)-1) for r in range(3) for col in range(3)}
        s=fixture(cells,config=c,taken=(0,0,0))
        out=apply_move(s,(0,0))
        self.assertEqual(out.state.status,Status.ABORTED)
        self.assertEqual(out.state.reason,"cascade_cycle")

    def test_incremental_matches_headless(self):
        ss=example_session(); a=apply_move(ss.state,(0,0))
        tx=MoveTransaction(ss.state,(0,0))
        while not tx.done: tx.advance()
        self.assertEqual(tx.result,a)

    def test_fuzz_conservation_turns_and_stability(self):
        # Test-only random input, never installed as an agent in the app.
        for seed in range(75):
            rng=random.Random(seed)
            rows,cols=((3,3),(6,5),(9,6))[seed%3]
            s=new_game(Config(rows=rows,cols=cols,move_limit=150))
            for _ in range(150):
                if s.status is not Status.PLAYING: break
                moves=legal_moves(s); self.assertTrue(moves)
                old_total=sum(c.count for c in s.board)
                old_eliminated=s.eliminated
                out=apply_move(s,rng.choice(moves))
                self.assertEqual(sum(c.count for c in out.state.board),old_total+1)
                self.assertTrue(old_eliminated <= out.state.eliminated)
                s=out.state
                validate_state(s)
            self.assertNotEqual(s.status,Status.PLAYING)


if __name__=="__main__": unittest.main()
