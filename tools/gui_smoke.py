"""Exercise the real Tk window with generated mouse/key events (no gameplay AI).

Run on a desktop, or: xvfb-run -a python tools/gui_smoke.py
The game engine and the renderer are identical in the pygame window adapter.
"""
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from chain_reaction.controller import Controller
from chain_reaction.render import Renderer,viewport,WIDTH,HEIGHT
from chain_reaction.window import TkWindow


def main():
    with tempfile.TemporaryDirectory() as root:
        model=Controller(data_dir=Path(root));model.storage_enabled=False
        r=Renderer();window=TkWindow(model,r,(1200,767))
        window.root.update()
        def click(x,y):
            window.draw();window.root.update()
            ox,oy,w,h=viewport(window.size())
            window.canvas.event_generate('<Button-1>',x=round(ox+x*w/WIDTH),y=round(oy+y*h/HEIGHT))
            window.root.update()
        click(462,804)
        assert model.started,'Start button failed'
        window.root.focus_force();window.root.update()
        window.root.event_generate('<KeyPress>',keysym='c');window.root.update()
        assert model.show_counts,'Keyboard count toggle failed'
        window.root.event_generate('<KeyPress>',keysym='space');window.root.update()
        assert model.paused,'Keyboard pause failed'
        window.root.event_generate('<KeyPress>',keysym='space');window.root.update()
        assert not model.paused,'Keyboard resume failed'
        x,y,s,_,_=r.board_geometry(model)
        click(x+s/2,y+s/2)
        assert model.busy,'Grid input failed'
        for _ in range(5):model.update(.1)
        assert model.state.move_number==1,'Move did not commit'
        window.draw();window.root.update()
        click(792,804)
        assert model.state.move_number==0,'Undo failed'
        click(1310,63)
        assert model.modal=='help','Help button failed'
        click(500,745)
        assert model.example and model.state.move_number==36,'Example load failed'
        x,y,s,_,_=r.board_geometry(model)
        click(x+s/2,y+s/2)
        click(630,804)
        assert model.paused and model.session.transaction.topples==1,'Step failed'
        click(792,804)
        assert not model.busy and model.state.move_number==36,'Undo during cascade failed'
        window.root.geometry('900x700');window.root.update()
        click(934,804)
        assert model.modal=='reset','Scaled click mapping failed'
        click(578,550)
        assert model.modal is None,'Cancel failed'
        window.root.geometry('1366x873');window.root.update()
        model.action('startpause') # resume
        model.notify('Example position: click A1 to trigger a chain reaction.',20)
        window.draw();window.root.update()
        output=Path(sys.argv[1]) if len(sys.argv)>1 else Path('gui-smoke.png')
        r.render(model).save(output)
        window.close()
        print('GUI smoke passed: Start, keyboard counts/pause/resume, placement, Undo, Help, example, Step, cascade Undo, resize, reset/cancel.')


if __name__=='__main__':main()
