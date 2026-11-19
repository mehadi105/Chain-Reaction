import json
import tempfile
import unittest
from pathlib import Path
from chain_reaction.engine import Config, Status
from chain_reaction.session import Session,example_session


class SessionTests(unittest.TestCase):
    def test_undo_placement(self):
        s=Session(); original=s.state; s.play((0,0)); self.assertTrue(s.undo())
        self.assertEqual(s.state,original); self.assertFalse(s.undo())

    def test_undo_full_cascade(self):
        s=example_session(); original=s.state; s.play((0,0)); s.undo()
        self.assertEqual(s.state,original)

    def test_cancel_inflight(self):
        s=example_session(); original=s.state; history=len(s.history)
        s.begin((0,0)); s.transaction.advance(); s.undo()
        self.assertEqual(s.state,original)
        self.assertEqual(len(s.history),history)
        self.assertIsNone(s.transaction)

    def test_reject_concurrent_moves(self):
        s=Session(); s.begin((0,0))
        with self.assertRaises(ValueError):s.begin((0,1))

    def test_reject_unfinished_commit_and_save(self):
        s=example_session(); s.begin((0,0))
        with self.assertRaises(ValueError):s.commit()
        with self.assertRaises(ValueError):s.to_document()

    def test_replay_roundtrip(self):
        s=example_session(); s.play((0,0),1.23)
        t=Session.from_document(s.to_document())
        self.assertEqual(s.state,t.state)
        self.assertEqual(len(s.history),len(t.history))
        self.assertEqual(t.history[-1].elapsed,1.23)

    def test_atomic_file_save_and_load(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'nested'/'match.json'; s=example_session()
            s.save(path); t=Session.load(path)
            self.assertEqual(s.state,t.state)
            self.assertFalse(list(path.parent.glob('.chain-reaction-*')))

    def test_invalid_replay_rejected(self):
        for doc in (None,{}, {'format':'other'}, {'format':'chain-reaction-replay','version':2}):
            with self.subTest(doc=doc),self.assertRaises(ValueError):Session.from_document(doc)

    def test_illegal_replay_rejected(self):
        doc=Session().to_document()
        doc['moves']=[{'row':0,'col':0},{'row':0,'col':0}]
        with self.assertRaises(ValueError):Session.from_document(doc)

    def test_nonfinite_duration_rejected(self):
        for val in (float('nan'),float('inf'),-1,True,'abc'):
            doc=Session().to_document(); doc['moves']=[{'row':0,'col':0,'turn_seconds':val}]
            with self.subTest(val=val),self.assertRaises(ValueError):Session.from_document(doc)

    def test_saved_winner_is_not_trusted(self):
        doc=example_session().to_document()
        doc['result']={'status':'won','winner':2}
        restored=Session.from_document(doc)
        self.assertEqual(restored.state.status,Status.PLAYING)
        self.assertIsNone(restored.state.winner)

    def test_replay_keeps_move_limit(self):
        s=Session(Config(move_limit=3))
        for rc in ((0,0),(0,2),(8,5)):s.play(rc)
        restored=Session.from_document(s.to_document())
        self.assertEqual(restored.state,s.state)


if __name__=="__main__": unittest.main()
