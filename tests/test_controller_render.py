import tempfile
import unittest
from pathlib import Path
from chain_reaction.controller import Controller
from chain_reaction.engine import Config, Status
from chain_reaction.render import Renderer,WIDTH,HEIGHT,to_logical,viewport
from chain_reaction.session import example_session


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.m=Controller(); self.m.storage_enabled=False

    def resolve(self):
        for _ in range(10000):
            self.m.update(.1)
            if not self.m.busy:return
        self.fail('Cascade did not finish')

    def test_start_then_play(self):
        self.m.place(0,0); self.assertEqual(self.m.state.move_number,0)
        self.m.action('startpause'); self.m.place(0,0); self.resolve()
        self.assertEqual(self.m.state.move_number,1)

    def test_pause_blocks_placement(self):
        self.m.action('startpause'); self.m.action('startpause'); self.m.place(0,0)
        self.assertFalse(self.m.busy)

    def test_pause_freezes_timer(self):
        self.m.action('startpause'); self.m.update(1)
        self.m.action('startpause'); self.m.update(2)
        self.assertEqual(self.m.turn_seconds,1)

    def test_pause_freezes_cascade(self):
        self.m.action('example'); self.m.place(0,0)
        self.m.action('startpause'); before=self.m.session.board
        self.m.update(2)
        self.assertEqual(self.m.session.board,before)
        self.assertEqual(self.m.progress,0)

    def test_step_advances_one_explosion(self):
        self.m.action('example'); self.m.place(0,0)
        self.m.action('step')
        self.assertTrue(self.m.paused)
        self.assertEqual(self.m.session.transaction.topples,1)
        self.m.update(2)
        self.assertEqual(self.m.session.transaction.topples,1)

    def test_stepping_to_completion(self):
        self.m.action('example'); self.m.place(0,0)
        for _ in range(20):
            if not self.m.busy:break
            self.m.action('step')
        self.assertEqual(self.m.state.move_number,37)
        self.assertEqual(self.m.session.history[-1].result.topples,5)

    def test_instant_matches_normal(self):
        self.m.action('example'); before=self.m.state
        self.m.place(0,0); self.m.speed=3; self.resolve()
        from chain_reaction.engine import apply_move
        self.assertEqual(self.m.state,apply_move(before,(0,0)).state)

    def test_reset_requires_confirmation(self):
        self.m.action('example'); self.m.action('reset')
        self.assertEqual(self.m.state.move_number,36)
        self.m.action('close'); self.assertEqual(self.m.state.move_number,36)
        self.m.action('reset'); self.m.action('confirm_reset')
        self.assertEqual(self.m.state.move_number,0)

    def test_setup_board_and_draw(self):
        self.m.action('new'); self.m.action('board:6:5'); self.m.action('limit:60')
        self.m.action('confirm_new')
        self.assertEqual((self.m.state.config.rows,self.m.state.config.cols),(6,5))
        self.assertEqual(self.m.state.config.move_limit,60)

    def test_modal_blocks_play_and_clock(self):
        self.m.action('startpause'); self.m.action('help'); self.m.place(0,0); self.m.update(4)
        self.assertFalse(self.m.busy); self.assertEqual(self.m.turn_seconds,0)

    def test_undo_cancels_effect(self):
        self.m.action('example'); before=self.m.state
        self.m.place(0,0); self.m.action('step'); self.m.action('undo')
        self.assertFalse(self.m.busy); self.assertIsNone(self.m.event)
        self.assertEqual(self.m.state,before)

    def test_keyboard_placement(self):
        self.m.key('enter'); self.m.key('right'); self.m.key('enter'); self.resolve()
        self.assertEqual(self.m.state.cell(0,1).owner,0)

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as root:
            self.m.data_dir=Path(root); self.m.storage_enabled=True
            self.m.action('example'); self.m.autosave(); before=self.m.state
            self.m.action('save'); self.assertTrue(Path(self.m.last_saved).exists())
            self.m.action('load'); self.m.action('confirm_load')
            self.assertEqual(self.m.state,before)


class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Renderer()

    def test_render_all_screens_inside_canvas(self):
        for action in (None,'example','help','new','reset','load'):
            m=Controller(); m.storage_enabled=False
            if action:m.action(action)
            im=self.r.render(m)
            self.assertEqual(im.size,(WIDTH,HEIGHT))
            for text,b in self.r.text_bounds:
                with self.subTest(action=action,text=text):
                    self.assertGreaterEqual(b[0],0); self.assertGreaterEqual(b[1],0)
                    self.assertLessEqual(b[2],WIDTH); self.assertLessEqual(b[3],HEIGHT)

    def test_all_grid_sizes_cell_hit_testing(self):
        for rows,cols in ((6,5),(9,6),(10,8),(16,12)):
            m=Controller(Config(rows=rows,cols=cols)); x,y,s,w,h=self.r.board_geometry(m)
            self.assertEqual(self.r.cell_at(m,(x+s/2,y+s/2)),(0,0))
            self.assertEqual(self.r.cell_at(m,(x+w-s/2,y+h-s/2)),(rows-1,cols-1))
            self.assertIsNone(self.r.cell_at(m,(x-1,y)))
            self.assertIsNone(self.r.cell_at(m,(x+w,y)))

    def test_letterbox_coordinate_conversion(self):
        for size in ((1440,920),(640,480),(1920,1080),(900,1400)):
            x,y,w,h=viewport(size)
            xx,yy=to_logical((x+w/2,y+h/2),size)
            self.assertAlmostEqual(xx,WIDTH/2);self.assertAlmostEqual(yy,HEIGHT/2)

    def test_mouse_clicks_start_and_board(self):
        m=Controller();m.storage_enabled=False
        self.r.render(m);self.r.click(m,(462,804))
        self.assertTrue(m.started)
        self.r.render(m);x,y,s,_,_=self.r.board_geometry(m)
        self.r.click(m,(x+s/2,y+s/2))
        self.assertTrue(m.busy)

    def test_dialog_does_not_click_through(self):
        m=Controller();m.action('help');self.r.render(m)
        self.r.click(m,(462,804))
        self.assertFalse(m.started)

    def test_no_accidental_text_overlaps_on_main_screen(self):
        m=Controller();m.action('example');self.r.render(m)
        bounds=self.r.text_bounds
        for i,(t,a) in enumerate(bounds):
            for u,b in bounds[i+1:]:
                iw=min(a[2],b[2])-max(a[0],b[0]); ih=min(a[3],b[3])-max(a[1],b[1])
                self.assertFalse(iw>1 and ih>1,f'Text overlaps: {t!r} with {u!r}')


if __name__=="__main__":unittest.main()
