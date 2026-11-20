"""Shared deterministic arena renderer (Pillow).

Pygame presents these frames and handles input. A small Tk fallback can present
exactly the same renderer when pygame is unavailable. No font files or generated
artwork are bundled; the game board, orbs and controls are drawn by code.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from .agents import AGENT_NAMES
from .controller import Controller, NAMES, SPEEDS
from .engine import Cell, EMPTY, Status, critical_mass

WIDTH, HEIGHT = 1440, 920
BG = "#07110d"
PANEL = "#0e1b15"
LINE = "#2a4636"
TEXT = "#f3fbf6"
MUTED = "#9bb5a6"
DIM = "#6d8b78"
GREEN = "#5ef0a0"
COLOURS = ((255, 80, 103), (92, 151, 255), (65, 233, 126))
LEFT = (36, 140, 296, 694)
CENTRE = (356, 140, 704, 694)
RIGHT = (1084, 140, 320, 694)


def rgb(hexval: str) -> tuple[int, int, int]:
    return tuple(int(hexval[i:i+2], 16) for i in (1, 3, 5))


def tint(col, factor: float):
    return tuple(int(x * factor) for x in col)


def as_rgb(col) -> tuple[int, int, int]:
    if isinstance(col, str):
        return rgb(col)
    return tuple(int(c) for c in col[:3])


def mix(a, b, t: float) -> tuple[int, int, int]:
    a, b = as_rgb(a), as_rgb(b)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


@dataclass(frozen=True)
class Hit:
    action: str
    rect: tuple[int, int, int, int]
    enabled: bool = True

    def contains(self, point):
        if point is None:
            return False
        x, y, w, h = self.rect
        return x <= point[0] < x + w and y <= point[1] < y + h


class Fonts:
    """Use installed system fonts; never copy system font files into the project."""
    def __init__(self):
        candidates = [
            ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
            ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            ("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
        ]
        self.paths = next(((a, b) for a, b in candidates if Path(a).is_file() and Path(b).is_file()), (None, None))

    @lru_cache(maxsize=64)
    def get(self, size: int, bold: bool = False):
        path = self.paths[int(bold)]
        return ImageFont.truetype(path, size) if path else ImageFont.load_default(size=size)


@lru_cache(maxsize=48)
def orb_sprite(player: int, radius: int) -> Image.Image:
    """Analytic sphere shading and a restrained halo. Cached and antialiased."""
    scale = 3
    rad = radius * scale
    span = rad * 4
    img = Image.new("RGBA", (span, span))
    pix = img.load()
    cx = cy = span / 2
    colour = COLOURS[player]
    for y in range(span):
        for x in range(span):
            nx, ny = (x - cx) / rad, (y - cy) / rad
            dist = math.hypot(nx, ny)
            if dist <= 1:
                nz = math.sqrt(max(0, 1 - nx * nx - ny * ny))
                diffuse = max(0, -0.35 * nx - 0.5 * ny + 0.78 * nz)
                shine = math.exp(-((nx + .31)**2 + (ny + .38)**2) / .045)
                out = tuple(min(255, int(v * (.24 + .72 * diffuse) + 155 * shine)) for v in colour)
                pix[x, y] = (*out, 255)
            elif dist < 1.9:
                alpha = int(35 * math.exp(-(dist - 1) * 5))
                pix[x, y] = (*colour, alpha)
    return img.resize((radius * 4, radius * 4), Image.Resampling.LANCZOS)


@lru_cache(maxsize=160)
def glow_sprite(colour: tuple[int, int, int], radius: int, alpha: int) -> Image.Image:
    size = radius * 2
    img = Image.new("RGBA", (size, size))
    pix = img.load()
    cx = cy = radius - 0.5
    for y in range(size):
        for x in range(size):
            dist = math.hypot(x - cx, y - cy) / radius
            if dist < 1:
                a = int(alpha * (1 - dist) ** 2)
                if a:
                    pix[x, y] = (*colour, a)
    return img


@lru_cache(maxsize=160)
def ring_sprite(radius: int, colour: tuple[int, int, int], alpha: int, width: int) -> Image.Image:
    pad = width + 2
    size = (radius + pad) * 2
    img = Image.new("RGBA", (size, size))
    ImageDraw.Draw(img).ellipse(
        (pad, pad, size - pad - 1, size - pad - 1),
        outline=(*colour, alpha),
        width=width,
    )
    return img


class Renderer:
    def __init__(self):
        self.fonts = Fonts()
        self.hits: list[Hit] = []
        self.mouse = None
        self.motion = 0.0
        self._last_age = 0.0
        self.img = Image.new("RGB", (WIDTH, HEIGHT), BG)
        self.draw = ImageDraw.Draw(self.img)
        self.background = self.make_background()
        self.text_bounds: list[tuple] = []

    def _sync_motion(self, model: Controller) -> None:
        delta = model.age - self._last_age
        self._last_age = model.age
        if delta > 0 and model.started and not model.paused and not model.modal:
            self.motion += min(delta, 0.1)

    def make_background(self):
        im = Image.new("RGB", (WIDTH, HEIGHT), BG)
        d = ImageDraw.Draw(im)
        top, bot = (10, 28, 22), (4, 9, 8)
        for y in range(HEIGHT):
            f = (y / (HEIGHT - 1)) ** 1.35
            d.line((0, y, WIDTH, y), fill=tuple(int(top[i] + (bot[i] - top[i]) * f) for i in range(3)))
        base = im.convert("RGBA")
        for sprite, pos in (
            (glow_sprite((36, 150, 96), 260, 64), (-80, -120)),
            (glow_sprite((36, 86, 160), 220, 42), (WIDTH - 300, HEIGHT - 280)),
            (glow_sprite((28, 120, 78), 140, 36), (1000, -40)),
        ):
            base.paste(sprite, pos, sprite)
        im = base.convert("RGB")
        d = ImageDraw.Draw(im)
        for x in range(20, WIDTH, 28):
            for y in range(20, HEIGHT, 28):
                d.point((x, y), fill=(16, 34, 26))
        for x in range(980, WIDTH + 80, 56):
            d.line((x, 0, x + 90, 86), fill=(16, 38, 30), width=1)
        return im

    def _blit(self, sprite: Image.Image, x: float, y: float) -> None:
        self.img.paste(sprite, (round(x - sprite.width / 2), round(y - sprite.height / 2)), sprite)

    def glow(self, colour, x, y, radius, alpha) -> None:
        radius, alpha = int(radius), int(alpha)
        if radius < 2 or alpha <= 2:
            return
        alpha = min(248, alpha) // 4 * 4
        self._blit(glow_sprite(tuple(as_rgb(colour)), radius, alpha), x, y)

    def ring(self, colour, x, y, radius, alpha, width=2) -> None:
        radius, alpha, width = int(radius), int(alpha), int(width)
        if radius < 2 or alpha <= 2:
            return
        alpha = min(248, max(4, alpha // 8 * 8))
        self._blit(ring_sprite(radius, tuple(as_rgb(colour)), alpha, max(1, width)), x, y)

    def box(self, rect, fill=PANEL, outline=LINE, radius=12, width=1):
        x, y, w, h = map(int, rect)
        self.draw.rounded_rectangle((x, y, x + w - 1, y + h - 1), radius=radius, fill=fill, outline=outline, width=width)
        if w > 28 and h > 18:
            sheen = mix(fill, (255, 255, 255), 0.14)
            self.draw.line((x + radius, y + 1, x + w - radius - 1, y + 1), fill=sheen)

    def text(self, text, x, y, size=16, colour=TEXT, bold=False, align="left", maxw=None):
        f = self.fonts.get(size, bold)
        if maxw:
            while self.draw.textlength(text, font=f) > maxw and len(text) > 2:
                text = text[:-2] + "…"
        anchor = {"left": "lt", "center": "mt", "right": "rt"}[align]
        b = self.draw.textbbox((x, y), text, font=f, anchor=anchor)
        self.text_bounds.append((text, b))
        self.draw.text((x, y), text, font=f, fill=colour, anchor=anchor)
        return b

    def para(self, text, x, y, width, size=14, colour=MUTED, lineheight=None):
        lineheight = lineheight or int(size * 1.55)
        f = self.fonts.get(size)
        yy = y
        for paragraph in text.split("\n"):
            line = ""
            for word in paragraph.split():
                trial = f"{line} {word}".strip()
                if line and self.draw.textlength(trial, font=f) > width:
                    self.text(line, x, yy, size, colour)
                    yy += lineheight
                    line = word
                else:
                    line = trial
            self.text(line, x, yy, size, colour)
            yy += lineheight
        return yy

    def label(self, text, x, y, colour=MUTED):
        self.text(text, x, y, 11, colour, True)

    def line(self, x1, y, x2, colour=LINE):
        self.draw.line((x1, y, x2, y), fill=colour)

    def orb(self, player, x, y, radius=12, alpha=255):
        sprite = orb_sprite(player, int(radius))
        if alpha != 255:
            sprite = sprite.copy()
            sprite.putalpha(sprite.getchannel("A").point(lambda a: a * alpha // 255))
        self.img.paste(sprite, (round(x - radius * 2), round(y - radius * 2)), sprite)

    def button(self, action, caption, rect, *, primary=False, enabled=True, selected=False):
        hit = Hit(action, tuple(map(int, rect)), enabled)
        self.hits.append(hit)
        hover = enabled and hit.contains(self.mouse)
        if not enabled:
            fill, border, col = "#0d1612", "#1a2b21", DIM
        elif primary:
            fill = "#c8ffdf" if hover else GREEN
            border = "#f4fff8" if hover else "#9dffc8"
            col = "#07140b"
        elif selected or hover:
            fill = "#1b3d2b" if selected else "#173224"
            border = GREEN if selected else "#74c896"
            col = TEXT
        else:
            fill, border, col = "#101c16", LINE, TEXT
        self.box(rect, fill, border, radius=9)
        x, y, w, h = rect
        self.text(caption, x + w/2, y + (h-16)/2, 14, col, primary or selected, "center")

    @staticmethod
    def board_geometry(model: Controller):
        c = model.state.config
        cell = min(58, 522 / c.rows, 520 / c.cols)
        w, h = cell * c.cols, cell * c.rows
        return (708 - w/2, 224 + (522 - h)/2, cell, w, h)

    def cell_at(self, model, point):
        if point is None:
            return None
        x, y, cell, w, h = self.board_geometry(model)
        if x <= point[0] < x+w and y <= point[1] < y+h:
            return (int((point[1]-y)/cell), int((point[0]-x)/cell))
        return None

    def render(self, model: Controller, mouse=None) -> Image.Image:
        self._sync_motion(model)
        self.img = self.background.copy()
        self.draw = ImageDraw.Draw(self.img)
        self.mouse = mouse
        self.hits = []
        self.text_bounds = []
        self.header(model)
        self.left_panel(model)
        self.arena(model)
        self.right_panel(model)
        self.footer(model)
        if model.modal:
            self.dialog(model)
        return self.img

    def header(self, m):
        pulse = 0.65 + 0.35 * math.sin(self.motion * 2.2)
        self.glow((70, 190, 130), 64, 66, 34, int(46 * pulse))
        self.orb(0, 53, 57, 10)
        self.orb(1, 75, 57, 10)
        self.orb(2, 64, 75, 10)
        self.text("CHAIN REACTION", 102, 38, 30, TEXT, True)
        self.text("MULTI-AGENT ARENA", 103, 78, 11, MUTED, True)
        self.draw.line((104, 104, 228, 104), fill=GREEN, width=2)
        self.box((1010, 45, 208, 36), "#11251a", "#2a573b", 18)
        self.glow(GREEN, 1028, 62, 10, int(70 * pulse))
        self.draw.ellipse((1024, 58, 1032, 66), fill=GREEN)
        self.text("LOCAL MULTIPLAYER", 1042, 56, 11, GREEN, True)
        self.button("help", "How to play", (1232, 43, 172, 40))
        self.line(36, 110, 1404)

    def left_panel(self, m):
        self.box((36, 140, 296, 94))
        self.label("PLAY MODE", 56, 158)
        self.text("Three local players", 56, 179, 21, TEXT, True)
        self.text("One computer. Take turns.", 56, 211, 12, MUTED)
        self.label("PLAYERS", 36, 254)
        state = m.state
        board = m.session.board
        totals = [[0, 0] for _ in range(3)]
        for c in board:
            if c.count:
                totals[c.owner][0] += c.count
                totals[c.owner][1] += 1
        actor = m.session.transaction.player if m.busy else state.current_player
        for p in range(3):
            y = 282 + p * 121
            active = p == actor and state.status is Status.PLAYING
            gone = p in state.eliminated
            colour = COLOURS[p]
            self.box((36, y, 296, 109), "#14281e" if active else PANEL,
                     colour if active else LINE, 10, 2 if active else 1)
            self.draw.rounded_rectangle((38, y+16, 43, y+93), radius=3, fill=colour if not gone else DIM)
            if active and not gone:
                self.glow(colour, 66, y+31, 20, 100)
            self.orb(p, 66, y+31, 11, 95 if gone else 255)
            self.text(f"{NAMES[p]}", 88, y+16, 20, colour if not gone else DIM, True)
            seat = {"human": "HUMAN", "Minimax + alpha-beta": "MINIMAX", "MCTS": "MCTS", "CP-SAT planner": "CP-SAT"}.get(m.seats[p], "HUMAN")
            self.hits.append(Hit(f"seat:{p}", (84, y + 40, 150, 18)))
            self.text(f"P{p+1}  ·  {seat}", 88, y+43, 10, GREEN if m.seats[p] != "human" else MUTED, True)
            tag = "OUT" if gone else ("WINNER" if state.winner == p else ("TURN" if active and m.started else "READY"))
            self.text(tag, 314, y+23, 10, colour if not gone else DIM, True, "right")
            self.line(56, y+65, 312)
            self.text(f"{totals[p][0]:02d}", 56, y+79, 17, TEXT, True)
            self.label("ORBS", 87, y+83)
            self.text(f"{totals[p][1]:02d}", 177, y+79, 17, TEXT, True)
            self.label("CELLS", 208, y+83)
        self.box((36, 654, 296, 180))
        self.label("AI AGENTS", 56, 674)
        self.text("Click a name here, or P1 · HUMAN above.", 56, 697, 12, MUTED)
        seated = m.seats[m.state.current_player]
        for i, txt in enumerate(AGENT_NAMES):
            self.hits.append(Hit(f"agent:{i}", (48, 722 + i * 24, 272, 22)))
            self.draw.ellipse((57, 731 + i*24, 62, 736 + i*24), fill=GREEN if seated == txt else DIM)
            self.text(txt, 73, 727 + i*24, 13, GREEN if seated == txt else TEXT)
        self.line(56, 799, 312)
        self.text("Click the same agent again to clear it.", 56, 813, 11, DIM)

    def arena(self, m):
        self.box(CENTRE, "#09120e", "#294435", 12)
        self.label("MATCH BOARD", 380, 160, GREEN)
        c = m.state.config
        cap = f"DRAW AT {c.move_limit} MOVES" if c.move_limit else "MOVE CAP OFF"
        self.text(cap, 1036, 160, 11, MUTED, False, "right")
        self.text(f"{c.cols} columns × {c.rows} rows", 380, 181, 12, MUTED)
        if m.example:
            self.text("EXAMPLE POSITION", 1036, 181, 11, "#e2c782", True, "right")
        x, y, cell, bw, bh = self.board_geometry(m)
        # Subtle extruded green frame, matching the original game's geometry.
        self.draw.rectangle((x-7, y-7, x+bw+7, y+bh+7), fill="#050c08", outline="#264c2e", width=1)
        self.draw.rectangle((x-3, y-3, x+bw+3, y+bh+3), outline="#365c2d", width=1)
        self.draw.rectangle((x, y, x+bw, y+bh), fill="#030905")
        for col in range(c.cols + 1):
            xx = round(x+col*cell)
            self.draw.line((xx, y, xx, y+bh), fill="#28592a", width=1)
            self.draw.line((xx, y, xx+5, y-6), fill="#28592a", width=1)
        for row in range(c.rows + 1):
            yy = round(y+row*cell)
            self.draw.line((x, yy, x+bw, yy), fill="#28592a", width=1)
        for col in range(c.cols):
            self.text(chr(65+col), x+(col+.5)*cell, y-23, 10, DIM, True, "center")
        for row in range(c.rows):
            self.text(str(row+1), x-17, y+(row+.5)*cell-6, 10, DIM, False, "right")
        board = list(m.session.board)
        e = m.event
        progress = max(0.0, min(1.0, m.progress))
        if e is not None and e.kind == "explode" and progress < 1:
            board = list(e.before)
            sr, sc = e.source
            idx = sr*c.cols+sc
            board[idx] = e.after[idx]
        hovered = self.cell_at(m, self.mouse) or m.focus_cell
        if hovered and not m.modal and m.started and not m.busy and not m.paused and m.state.status is Status.PLAYING:
            r, cc = hovered
            owner = board[r*c.cols+cc].owner
            good = owner in (-1, m.state.current_player)
            color = COLOURS[m.state.current_player] if good else (155, 65, 72)
            self.draw.rectangle((x+cc*cell+2, y+r*cell+2, x+(cc+1)*cell-2, y+(r+1)*cell-2),
                                fill=tint(color, .09), outline=tint(color, .6), width=1)
            if good and owner == -1:
                self.orb(m.state.current_player, x+(cc+.5)*cell, y+(r+.5)*cell, round(cell*.17), 85)
            if not good:
                cx, cy = x+(cc+.5)*cell, y+(r+.5)*cell
                self.draw.line((cx-9, cy-9, cx+9, cy+9), fill=color, width=2)
                self.draw.line((cx-9, cy+9, cx+9, cy-9), fill=color, width=2)
        for idx, cc in enumerate(board):
            if not cc.count:
                continue
            r, col = divmod(idx, c.cols)
            cx, cy = x+(col+.5)*cell, y+(r+.5)*cell
            critical = cc.count >= critical_mass(c, r, col)-1
            # Ambient tremor freezes on Pause / modal so inspection is deterministic.
            tremor = (math.sin(m.age*7 + idx)*.65 if critical and not m.paused and not m.modal else 0)
            if cc.count == 1:
                points = [(0, 0)]
            elif cc.count == 2:
                points = [(-.14*cell, 0), (.14*cell, 0)]
            else:
                points = [(0, -.15*cell), (-.145*cell, .105*cell), (.145*cell, .105*cell)]
            rad = round(cell*(.198 if cc.count == 1 else .17))
            for dx, dy in points:
                self.orb(cc.owner, cx+dx+tremor, cy+dy, rad)
            if m.show_counts or cc.count > 3:
                self.box((int(x+(col+1)*cell-19), int(y+r*cell+4), 14, 15), "#102017", "#304b38", 3)
                self.text(str(cc.count), x+(col+1)*cell-12, y+r*cell+6, 9, TEXT, True, "center")
            if critical:
                colr = tint(COLOURS[cc.owner], .6)
                self.draw.line((cx-7, y+(r+1)*cell-5, cx+7, y+(r+1)*cell-5), fill=colr, width=1)
        if m.selected:
            r, cc = m.selected
            xx, yy = x+cc*cell, y+r*cell
            colr = "#aac3b0"
            for sx, sy, dx, dy in ((xx+3, yy+3, 1, 1), (xx+cell-3, yy+3, -1, 1),
                                  (xx+3, yy+cell-3, 1, -1), (xx+cell-3, yy+cell-3, -1, -1)):
                self.draw.line((sx, sy, sx+dx*8, sy), fill=colr)
                self.draw.line((sx, sy, sx, sy+dy*8), fill=colr)
        if e is not None and progress < 1:
            sr, sc = e.source
            sx, sy = x+(sc+.5)*cell, y+(sr+.5)*cell
            if e.kind == "explode":
                t = progress*progress*(3-2*progress)
                for tr, tc in e.targets:
                    tx, ty = x+(tc+.5)*cell, y+(tr+.5)*cell
                    self.orb(e.player, sx+(tx-sx)*t, sy+(ty-sy)*t, max(6, round(cell*.16)))
                rr = cell*(.1+.3*progress)
                self.draw.ellipse((sx-rr, sy-rr, sx+rr, sy+rr), outline=tint(COLOURS[e.player], .7*(1-progress)), width=2)
            else:
                rr = cell*(.19+.17*progress)
                self.draw.ellipse((sx-rr, sy-rr, sx+rr, sy+rr), outline=tint(COLOURS[e.player], .5*(1-progress)), width=1)
        if not m.started:
            self.board_banner("Ready to react?", "Start the match. Red places the first orb.", GREEN)
        elif not m.busy and m.state.status is not Status.PLAYING:
            if m.state.status is Status.WON:
                self.board_banner(f"{NAMES[m.state.winner]} wins", "Last colour standing.", COLOURS[m.state.winner])
            elif m.state.status is Status.DRAW:
                self.board_banner("Draw", "The optional move limit has been reached.", "#e2c782")
            else:
                self.board_banner("Safety stop", "Cascade stopped. Undo or reset; not a draw.", "#e2c782")
        elif m.paused:
            self.box((835, 207, 190, 32), "#13241a", "#4b7157", 5)
            self.text("PAUSED  /  . TO STEP", 930, 217, 10, GREEN, True, "center")
        hint = "Place only in an empty cell or your own colour."
        self.text(hint, 708, 759, 12, MUTED, False, "center")
        terminal = not m.busy and m.state.status is not Status.PLAYING
        start = "New match" if terminal else ("Start" if not m.started else ("Resume" if m.paused else "Pause"))
        self.button("startpause", start, (380, 784, 164, 40), primary=True)
        self.button("step", "Step", (554, 784, 152, 40), enabled=m.busy)
        self.button("undo", "Undo", (716, 784, 152, 40), enabled=m.busy or bool(m.session.history))
        self.button("reset", "Reset", (878, 784, 158, 40))

    def board_banner(self, title, subtitle, colour):
        self.box((444, 430, 528, 105), "#0d1b13", "#42634c", 9)
        self.text(title, 708, 451, 27, colour, True, "center")
        self.text(subtitle, 708, 493, 13, MUTED, False, "center")

    def right_panel(self, m):
        self.box((1084, 140, 320, 162))
        self.label("LIVE STATUS", 1104, 159)
        state = m.state
        p = m.session.transaction.player if m.busy else state.current_player
        colour = COLOURS[p]
        label = "READY" if not m.started else ("PAUSED" if m.paused else ("REACTING" if m.busy else "LIVE"))
        if state.status is not Status.PLAYING and not m.busy:
            label = "FINISHED"
        self.text(label, 1384, 159, 10, GREEN if label == "LIVE" else MUTED, True, "right")
        title = f"{NAMES[p]} to move"
        if m.busy:
            title = "Chain reaction"
        elif state.status is Status.WON:
            title, colour = f"{NAMES[state.winner]} wins", COLOURS[state.winner]
        elif state.status is Status.DRAW:
            title = "Move-limit draw"
        elif state.status is Status.ABORTED:
            title = "Match stopped"
        beat = 0.55 + 0.45 * math.sin(self.motion * (6.2 if m.busy else 2.6))
        self.glow(colour, 1108, 198, 13, int(120 * beat))
        self.draw.ellipse((1103, 193, 1113, 203), fill=colour)
        self.text(title, 1123, 184, 23, TEXT, True)
        self.text(f"Turn time  {m.turn_seconds:04.1f}s", 1104, 223, 12, MUTED)
        self.line(1104, 247, 1384)
        count = state.move_number + (1 if m.busy else 0)
        orbs = sum(cell.count for cell in m.session.board)
        tx = m.session.transaction
        bursts = tx.topples if tx else (m.session.history[-1].result.topples if m.session.history else 0)
        for xx, n, label in ((1104, count, "MOVES"), (1205, orbs, "ORBS"), (1303, bursts, "BURSTS")):
            self.draw.rounded_rectangle((xx-8, 254, xx+78, 284), radius=7, fill="#13261c", outline="#243c2e")
            self.text(str(n).zfill(2), xx, 259, 18, TEXT, True)
            self.label(label, xx+33, 265, DIM)
        self.box((1084, 322, 320, 290))
        self.label("RECENT MOVES", 1104, 342)
        self.text(f"{len(m.session.history)} total", 1384, 342, 10, DIM, False, "right")
        history = list(reversed(m.session.history))
        maxscroll = max(0, len(history)-5)
        m.log_scroll = max(0, min(maxscroll, m.log_scroll))
        if not history:
            self.text("Your story starts here.", 1104, 401, 15, MUTED, True)
            self.para("Place an orb to record your first move. Captures and explosions appear here.",
                      1104, 433, 268, 13, DIM)
        for j, record in enumerate(history[m.log_scroll:m.log_scroll+5]):
            y = 373 + j*44
            result = record.result
            rr, cc = result.move
            if j == 0 and m.log_scroll == 0:
                self.draw.rounded_rectangle((1096, y-4, 1392, y+32), radius=6, fill="#14281e")
            self.text(str(record.result.state.move_number).zfill(2), 1104, y+3, 11, DIM)
            self.draw.ellipse((1132, y+5, 1138, y+11), fill=COLOURS[result.player])
            self.text(f"{NAMES[result.player]}  →  {chr(65+cc)}{rr+1}", 1148, y, 13, TEXT, True)
            detail = f"{result.topples} bursts · {result.captures} captures" if result.topples else "Orb placed"
            self.text(detail, 1148, y+20, 10, MUTED)
            if j < 4:
                self.line(1104, y+37, 1384, "#182a20")
        if len(history)>5:
            self.text("Scroll here to see earlier turns", 1244, 596, 9, DIM, False, "center")
        self.box((1084, 632, 320, 202))
        self.label("MATCH TOOLS", 1104, 652)
        self.button("speed", f"Speed: {SPEEDS[m.speed]}", (1104, 677, 137, 36))
        self.button("counts", "Counts: on" if m.show_counts else "Counts: off", (1251, 677, 133, 36), selected=m.show_counts)
        self.button("save", "Save replay", (1104, 723, 137, 36), enabled=not m.busy)
        self.button("load", "Load save", (1251, 723, 133, 36))
        self.button("new", "New match / board settings", (1104, 769, 280, 36))
        self.text("Autosaves after each completed move", 1244, 816, 10, DIM, False, "center")

    def footer(self, m):
        self.line(36, 855, 1404)
        if m.age < m.message_until:
            self.text(m.message, 36, 867, 13, MUTED, maxw=1368)
        else:
            self.text("SPACE  pause / resume     .  step     U  undo     H  help     F11  fullscreen", 36, 867, 11, MUTED)
        team = "Mynul Hassan Mehadi · 2207105     /     Ahnaf Tajwar · 2207104     /     Al-Amin · 1707055"
        self.text(team, 36, 897, 10, DIM)
        self.text("CSE 3210   /   GAME ENGINE BUILD 01", 1404, 897, 10, DIM, True, "right")

    def dialog(self, m):
        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 184))
        self.img = Image.alpha_composite(self.img.convert("RGBA"), overlay).convert("RGB")
        self.draw = ImageDraw.Draw(self.img)
        self.hits = []  # background controls cannot receive modal clicks
        if m.modal == "help":
            self.box((340, 148, 760, 640), "#0e1c14", "#41644b", 16)
            self.draw.line((368, 152, 1072, 152), fill=GREEN, width=3)
            self.label("THE RULES", 376, 178, GREEN)
            self.text("Small moves. Big reactions.", 376, 204, 28, TEXT, True)
            rules = [
                ("01", "Place one orb", "Click an empty cell or a cell of your own colour. No direct enemy placement."),
                ("02", "Reach the limit", "Corners explode at 2 orbs; edges at 3; interior cells at 4."),
                ("03", "Capture and cascade", "One orb travels up, right, down and left where a neighbour exists. All orbs in captured cells change colour."),
                ("04", "Last colour wins", "After all players take a first turn, a player with no orbs is out. Skip that player's turns."),
            ]
            yy = 259
            for n, h, desc in rules:
                self.text(n, 376, yy+2, 12, GREEN, True)
                self.text(h, 416, yy, 17, TEXT, True)
                end = self.para(desc, 416, yy+27, 638, 13, MUTED, 20)
                yy = end + 25
            self.line(376, 618, 1064)
            self.para("Space pauses. The period key (.) steps through an active cascade. U undoes a move. C toggles counts. Arrow keys + Enter place an orb. F11 toggles fullscreen.",
                      376, 637, 688, 13, MUTED, 20)
            self.text("The example replaces the current board. Save a replay first to keep it.", 376, 695, 11, DIM)
            self.button("example", "Try a cascade example", (376, 724, 250, 42))
            self.button("close", "Back to game", (814, 724, 250, 42), primary=True)
        elif m.modal == "new":
            self.box((405, 198, 630, 510), "#0e1c14", "#41644b", 16)
            self.draw.line((430, 202, 1010, 202), fill=GREEN, width=3)
            self.label("LOCAL MULTIPLAYER", 439, 230, GREEN)
            self.text("Set up a new match", 439, 258, 29, TEXT, True)
            self.para("Three human players. AI algorithms are not included yet. Starting a new match replaces the current board.", 439, 304, 558, 14)
            self.label("BOARD SIZE", 439, 374)
            for i, (r, c, label) in enumerate(((6, 5, "Compact 5 × 6"), (9, 6, "Classic 6 × 9"), (10, 8, "Large 8 × 10"))):
                self.button(f"board:{r}:{c}", label, (439+i*189, 398, 180, 44), selected=m.draft_board == (r,c))
            self.label("OPTIONAL MOVE-LIMIT DRAW", 439, 478)
            for i, (v, label) in enumerate(((0, "Off (default)"), (60, "60 moves"), (100, "100 moves"))):
                self.button(f"limit:{v}", label, (439+i*189, 503, 180, 40), selected=(m.draft_limit or 0)==v)
            self.para("An extra tournament rule, not a classic rule. Counts total moves across all players; a win takes priority.", 439, 559, 558, 12)
            self.button("close", "Cancel", (439, 638, 170, 42))
            self.button("confirm_new", "Start new match", (749, 638, 252, 42), primary=True)
        else:
            self.box((430, 297, 580, 306), "#0e1c14", "#41644b", 16)
            self.draw.line((456, 301, 984, 301), fill=GREEN, width=3)
            loading = m.modal == "load"
            title = "Load the last autosave?" if loading else "Reset this match?"
            body = ("The saved match is replayed and validated before loading. Your current unsaved position will be replaced."
                    if loading else "This clears the board and move history. Board size and optional move-limit settings stay the same.")
            self.text(title, 464, 337, 26, TEXT, True)
            self.para(body, 464, 389, 512, 16)
            self.button("close", "Cancel", (464, 528, 230, 42))
            self.button("confirm_load" if loading else "confirm_reset", "Load save" if loading else "Reset match", (710, 528, 266, 42), primary=True)

    def click(self, model, point):
        for hit in reversed(self.hits):
            if hit.enabled and hit.contains(point):
                model.action(hit.action)
                return
        if not model.modal:
            cell = self.cell_at(model, point)
            if cell:
                model.place(*cell)

    def scroll(self, model, point, amount):
        if point and not model.modal and Hit("log", (1084,322,320,290)).contains(point):
            model.log_scroll = max(0, min(max(0, len(model.session.history)-5), model.log_scroll + amount))


def viewport(size: tuple[int,int]):
    scale = min(size[0] / WIDTH, size[1] / HEIGHT)
    w, h = max(1, round(WIDTH*scale)), max(1, round(HEIGHT*scale))
    return ((size[0]-w)//2, (size[1]-h)//2, w, h)


def to_logical(point, size):
    x, y, w, h = viewport(size)
    if x <= point[0] < x+w and y <= point[1] < y+h:
        return ((point[0]-x)*WIDTH/w, (point[1]-y)*HEIGHT/h)
    return None


def scaled_frame(image, size):
    x, y, w, h = viewport(size)
    if size == (WIDTH, HEIGHT):
        return image
    canvas = Image.new("RGB", size, "#040806")
    frame = image.resize((w,h), Image.Resampling.LANCZOS)
    canvas.paste(frame,(x,y))
    return canvas
