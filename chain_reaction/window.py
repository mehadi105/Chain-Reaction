"""Window/input adapters. Pygame is primary; Tk is an optional fallback."""
from __future__ import annotations
import time
from .controller import Controller
from .engine import Status
from .render import Renderer, WIDTH, HEIGHT, scaled_frame, to_logical, viewport


def _open_screen(size, flags):
    import pygame
    try:
        return pygame.display.set_mode(size, flags, vsync=1)
    except TypeError:
        return pygame.display.set_mode(size, flags)


def _present(screen, image):
    import pygame
    size = screen.get_size()
    surface = pygame.image.frombytes(image.tobytes(), image.size, "RGB")
    x, y, w, h = viewport(size)
    if (w, h) != image.size:
        surface = pygame.transform.smoothscale(surface, (w, h))
    surface = surface.convert()
    if (w, h) != size:
        screen.fill((5, 10, 8))
        screen.blit(surface, (x, y))
    else:
        screen.blit(surface, (0, 0))


def _cursor(model: Controller, renderer: Renderer, mouse):
    import pygame
    hand = False
    if mouse is not None:
        hand = any(hit.enabled and hit.contains(mouse) for hit in renderer.hits)
        if not hand and not model.modal and model.started and not model.busy and not model.paused and model.state.status is Status.PLAYING:
            cell = renderer.cell_at(model, mouse)
            if cell:
                row, col = cell
                owner = model.session.board[row * model.state.config.cols + col].owner
                hand = owner in (-1, model.state.current_player)
    try:
        pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if hand else pygame.SYSTEM_CURSOR_ARROW)
    except (pygame.error, AttributeError):
        pass


def run_pygame(model: Controller, renderer: Renderer, size=(1366, 873), frames=0):
    import pygame
    pygame.display.init()
    desktop = pygame.display.get_desktop_sizes()[0]
    initial = (min(size[0], max(640, desktop[0]-80)), min(size[1], max(480, desktop[1]-160)))
    screen = _open_screen(initial, pygame.RESIZABLE)
    pygame.display.set_caption("Chain Reaction | Three-player local arena")
    clock = pygame.time.Clock()
    mouse = None
    fullscreen = False
    windowed_size = initial
    alive = True
    count = 0
    while alive:
        dt = clock.tick(60) / 1000
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                alive = False
            elif event.type == pygame.VIDEORESIZE and not fullscreen:
                screen = _open_screen((max(640, event.w), max(480, event.h)), pygame.RESIZABLE)
            elif event.type == pygame.MOUSEMOTION:
                mouse = to_logical(event.pos, screen.get_size())
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse = to_logical(event.pos, screen.get_size())
                renderer.click(model, mouse)
            elif event.type == pygame.MOUSEWHEEL:
                renderer.scroll(model, to_logical(pygame.mouse.get_pos(),screen.get_size()), event.y)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    fullscreen = not fullscreen
                    if fullscreen:
                        windowed_size = screen.get_size()
                        screen = _open_screen(desktop, pygame.FULLSCREEN)
                    else:
                        screen = _open_screen(windowed_size, pygame.RESIZABLE)
                else:
                    name = pygame.key.name(event.key).lower()
                    model.key({"return":"enter", "keypad enter":"enter", "space":"space"}.get(name,name))
            elif event.type == getattr(pygame,"WINDOWFOCUSLOST",-1):
                if model.started:
                    model.paused = True
        model.update(dt)
        frame = renderer.render(model, mouse)
        _present(screen, frame)
        _cursor(model, renderer, mouse)
        pygame.display.flip()
        count += 1
        if frames and count >= frames:
            alive = False
    if model.started and not model.busy:
        model.autosave()
    pygame.quit()


class TkWindow:
    """Same game and renderer, standard-library window adapter for fallback/testing."""
    def __init__(self, model: Controller, renderer: Renderer, size=(1366,873)):
        import tkinter as tk
        from PIL import ImageTk
        self.tk = tk
        self.ImageTk = ImageTk
        self.model, self.renderer = model, renderer
        self.root = tk.Tk()
        self.root.title("Chain Reaction | Three-player local arena")
        w = min(size[0], max(640, self.root.winfo_screenwidth()-70))
        h = min(size[1], max(480, self.root.winfo_screenheight()-90))
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(640,480)
        self.canvas = tk.Canvas(self.root, bg="#040806", highlightthickness=0, bd=0)
        self.canvas.pack(fill="both",expand=True)
        self.item = self.canvas.create_image(0,0,anchor="nw")
        self.photo = None
        self.mouse = None
        self.fullscreen = False
        self.alive = True
        self.frame_count = 0
        self.last_time = time.perf_counter()
        self.root.protocol("WM_DELETE_WINDOW",self.close)
        self.canvas.bind("<Motion>",self.motion)
        self.canvas.bind("<Button-1>",self.click)
        self.canvas.bind("<MouseWheel>",self.scroll)
        self.canvas.bind("<Button-4>",lambda e:self.renderer.scroll(self.model,self.mouse,1))
        self.canvas.bind("<Button-5>",lambda e:self.renderer.scroll(self.model,self.mouse,-1))
        self.root.bind("<KeyPress>",self.key)
        self.root.update_idletasks()
        self.draw()

    def size(self):
        return (max(1,self.canvas.winfo_width()),max(1,self.canvas.winfo_height()))

    def motion(self,event):
        self.mouse = to_logical((event.x,event.y),self.size())

    def click(self,event):
        self.motion(event)
        self.renderer.click(self.model,self.mouse)

    def scroll(self,event):
        self.motion(event)
        amount = 1 if event.delta > 0 else -1
        self.renderer.scroll(self.model,self.mouse,amount)

    def key(self,event):
        name = event.keysym.lower()
        if name == "f11":
            self.fullscreen = not self.fullscreen
            self.root.attributes("-fullscreen", self.fullscreen)
        else:
            self.model.key({"return":"enter", "kp_enter":"enter", "period":".", "space":"space"}.get(name,name))

    def draw(self):
        frame = scaled_frame(self.renderer.render(self.model,self.mouse),self.size())
        self.photo = self.ImageTk.PhotoImage(frame)
        self.canvas.itemconfigure(self.item,image=self.photo)
        self.frame_count += 1

    def tick(self, frames=0):
        if not self.alive:
            return
        now = time.perf_counter()
        self.model.update(now-self.last_time)
        self.last_time = now
        start = time.perf_counter()
        self.draw()
        if frames and self.frame_count >= frames:
            self.close()
            return
        # Render at up to 30 fps; rule processing is frame-rate independent.
        delay = max(1,round((1/30-(time.perf_counter()-start))*1000))
        self.root.after(delay,lambda:self.tick(frames))

    def close(self):
        if self.alive:
            if self.model.started and not self.model.busy:
                self.model.autosave()
            self.alive=False
            self.root.destroy()

    def run(self,frames=0):
        self.tick(frames)
        self.root.mainloop()


def run_tk(model,renderer,size=(1366,873),frames=0):
    TkWindow(model,renderer,size).run(frames)
