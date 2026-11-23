"""Build the CSE 3210 evaluation deck in the 2207104 proposal format."""
from __future__ import annotations
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent
FIG = ROOT / "figures"
OUT = ROOT / "CSE3210-Chain-Reaction-Slides.pptx"
BG_IMAGE = FIG / "deck-bg.png"

INK = "08110F"
CARD = "0C1713"
WHITE = "F2F6F3"
BODY = "B1C0B8"
MUTED = "869D90"
TEAL = "63DFC9"
GREEN = "50EE82"
RED = "FF6571"
BLUE = "789BFF"
LINE = "2B493B"
FRAME = "040B07"

W, H = 13.333, 7.5
TOTAL = 21


def font(size, bold=False):
    path = "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf"
    return ImageFont.truetype(path, size)


def rounded(draw, box, fill, outline, width=3, radius=18):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def center_text(draw, box, lines, fill, size, bold=False):
    fnt = font(size, bold)
    heights, widths = [], []
    for line in lines:
        left, top, right, bottom = draw.textbbox((0, 0), line, font=fnt)
        widths.append(right - left)
        heights.append(bottom - top)
    total = sum(heights) + 6 * (len(lines) - 1)
    y = box[1] + (box[3] - box[1] - total) / 2
    for line, width, height in zip(lines, widths, heights):
        x = box[0] + (box[2] - box[0] - width) / 2
        draw.text((x, y), line, font=fnt, fill=fill)
        y += height + 6


def draw_minimax():
    image = Image.new("RGB", (1600, 860), "#08110F")
    draw = ImageDraw.Draw(image)
    root = (620, 36, 980, 126)
    rounded(draw, root, "#0C1713", "#50EE82")
    center_text(draw, root, ["Red to move"], "#F2F6F3", 28, True)
    children = [
        ((70, 250, 330, 430), ["(1, 1)", "value 1", "terminal win"], "#0C1713", "#50EE82"),
        ((360, 250, 620, 430), ["(0, 0)", "cut at 0.0476", "first reply only"], "#0C1713", "#FF6571"),
        ((650, 250, 910, 430), ["(0, 2)", "cut at 0.0476", "first reply only"], "#0C1713", "#FF6571"),
        ((940, 250, 1200, 430), ["(2, 0)", "cut at 0.0476", "first reply only"], "#0C1713", "#FF6571"),
        ((1230, 250, 1490, 430), ["(2, 2)", "cut at 0.0476", "first reply only"], "#0C1713", "#FF6571"),
    ]
    rx = (root[0] + root[2]) // 2
    for box, lines, fill, outline in children:
        cx = (box[0] + box[2]) // 2
        draw.line((rx, root[3], cx, box[1]), fill="#2B493B", width=3)
        rounded(draw, box, fill, outline)
        center_text(draw, box, lines, "#F2F6F3", 24, True)
    reply = (360, 560, 700, 760)
    draw.line((490, 430, 530, 560), fill="#789BFF", width=3)
    rounded(draw, reply, "#0C1713", "#789BFF")
    center_text(draw, reply, ["Blue plays (0, 1)", "utility 0.0476", "then cutoff"], "#F2F6F3", 24, True)
    note = (760, 560, 1490, 760)
    rounded(draw, note, "#0C1713", "#2B493B")
    center_text(
        draw, note,
        ["(1, 1) is searched first because it explodes.", "It returns 1, so alpha becomes 1.", "Every later reply is below 1 and is cut."],
        "#B1C0B8", 22, False,
    )
    image.save(FIG / "tree-minimax.png")


def draw_mcts():
    image = Image.new("RGB", (1600, 860), "#08110F")
    draw = ImageDraw.Draw(image)
    root = (620, 36, 980, 140)
    rounded(draw, root, "#0C1713", "#50EE82")
    center_text(draw, root, ["40 iterations", "seed 1"], "#F2F6F3", 26, True)
    nodes = [
        ((70, 300, 350, 520), ["(1, 1)", "29 visits", "mean 1.00"], "#0C1713", "#50EE82"),
        ((380, 300, 660, 520), ["(2, 0)", "8 visits", "mean 0.39"], "#0C1713", "#2B493B"),
        ((690, 300, 970, 520), ["(0, 0)", "4 visits", "mean −0.21"], "#0C1713", "#2B493B"),
        ((1000, 300, 1280, 520), ["(0, 2)", "2 visits", "mean −0.43"], "#0C1713", "#2B493B"),
        ((1310, 300, 1550, 520), ["(2, 2)", "2 visits", "mean −0.43"], "#0C1713", "#2B493B"),
    ]
    rx = (root[0] + root[2]) // 2
    for box, lines, fill, outline in nodes:
        cx = (box[0] + box[2]) // 2
        draw.line((rx, root[3], cx, box[1]), fill="#2B493B", width=3)
        rounded(draw, box, fill, outline)
        center_text(draw, box, lines, "#F2F6F3", 24, True)
    note = (180, 620, 1420, 790)
    rounded(draw, note, "#0C1713", "#2B493B")
    center_text(
        draw, note,
        ["The move played is the child with the most visits.", "(1, 1) was visited 29 times and every sample was a win."],
        "#B1C0B8", 24, False,
    )
    image.save(FIG / "tree-mcts.png")


def rgb(value):
    return RGBColor.from_string(value)


def _solid(shape):
    return shape._element.spPr.find(qn("a:solidFill"))


def paint(shape, color, alpha=None, line=None, line_width=9525):
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(color)
    if alpha is not None:
        srgb = _solid(shape).find(qn("a:srgbClr"))
        srgb.append(etree.Element(qn("a:alpha"), {"val": str(int(alpha))}))
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = rgb(line)
        shape.line.width = Emu(line_width)


def rule(slide, x, y, w, color=LINE, width=9525, vertical=False):
    if vertical:
        shape = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x), Inches(y), Inches(x), Inches(y + w))
    else:
        shape = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x), Inches(y), Inches(x + w), Inches(y))
    shape.line.color.rgb = rgb(color)
    shape.line.width = Emu(width)
    return shape


def text(slide, lines, x, y, w, h, size, color, bold=False, align=PP_ALIGN.LEFT):
    if isinstance(lines, str):
        lines = [lines]
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.word_wrap = True
    frame.auto_size = None
    frame.margin_left = Emu(0)
    frame.margin_right = Emu(0)
    frame.margin_top = Emu(0)
    frame.margin_bottom = Emu(0)
    for index, line in enumerate(lines):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = align
        paragraph.space_before = Pt(0)
        paragraph.space_after = Pt(0)
        run = paragraph.add_run()
        run.text = line
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.name = "Arial"
        run.font.color.rgb = rgb(color)
    return box


def footer(slide, number):
    rule(slide, 0.70, 7.04, 11.93)
    text(slide, "CSE 3210  •  ARTIFICIAL INTELLIGENCE LABORATORY", 0.70, 7.16, 9.70, 0.22, 11, MUTED)
    text(slide, f"{number:02d}  /  {TOTAL:02d}", 11.20, 7.14, 1.43, 0.24, 12, MUTED, align=PP_ALIGN.RIGHT)


def backdrop(slide):
    slide.shapes.add_picture(str(BG_IMAGE), Inches(0), Inches(0), Inches(W), Inches(H))
    tint = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(W), Inches(H))
    paint(tint, INK, alpha=12000)


def content_slide(prs, label, title, number):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    backdrop(slide)
    text(slide, label, 0.70, 0.36, 10.4, 0.28, 13, TEAL, True)
    text(slide, title, 0.70, 0.70, 10.9, 0.58, 31, WHITE, True)
    text(slide, f"{number:02d}", 12.03, 0.78, 0.70, 0.32, 16, GREEN, True, PP_ALIGN.RIGHT)
    rule(slide, 0.70, 1.46, 11.93)
    footer(slide, number)
    return slide


def title_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    backdrop(slide)
    panel = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(7.10), Inches(7.02))
    paint(panel, INK, alpha=94000)
    text(slide, "CSE 3210  •  AI LAB FINAL EVALUATION", 0.70, 0.54, 6.00, 0.28, 13, TEAL, True)
    rule(slide, 0.70, 1.03, 0.83, GREEN, 19050)
    text(slide, ["CHAIN", "REACTION"], 0.70, 1.55, 6.20, 1.70, 52, WHITE, True)
    text(slide, "Multi-Agent AI Battle Arena", 0.70, 3.48, 6.15, 0.46, 24, GREEN, True)
    text(slide, ["Three search agents.", "One shared 9×6 board."], 0.70, 4.12, 6.12, 0.80, 20, BODY)
    text(slide, "PRESENTED BY", 0.70, 5.20, 5.80, 0.26, 13, TEAL, True)
    text(slide, "Mynul Hassan Mehadi (2207105)", 0.70, 5.58, 6.10, 0.30, 16, BODY)
    text(slide, "Ahnaf Tajwar (2207104)", 0.70, 5.92, 6.10, 0.30, 16, BODY)
    text(slide, "Al-Amin (1707055)", 0.70, 6.26, 6.10, 0.30, 16, BODY)
    footer(slide, 1)
    return slide


def item(slide, number, heading, body, x, y, w):
    text(slide, number, x, y, 0.50, 0.28, 14, GREEN, True)
    text(slide, heading, x + 0.58, y - 0.02, w - 0.58, 0.36, 20, WHITE, True)
    text(slide, body, x + 0.58, y + 0.40, w - 0.58, 0.70, 16, BODY)


def veil(slide, x, y, w, h):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    paint(shape, CARD, alpha=94000, line=LINE)
    return shape


def card(slide, x, y, w, h, accent):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    paint(shape, CARD, alpha=92000, line=LINE)
    rule(slide, x, y, w, accent, 25400)
    return shape


def build():
    draw_minimax()
    draw_mcts()
    prs = Presentation()
    prs.slide_width = Inches(W)
    prs.slide_height = Inches(H)
    prs.core_properties.title = "CSE 3210 Chain Reaction"
    prs.core_properties.author = "Mynul Hassan Mehadi, Ahnaf Tajwar, Al-Amin"
    prs.core_properties.subject = "Artificial Intelligence Laboratory final evaluation"

    title_slide(prs)

    slide = content_slide(prs, "THE GAME", "Placement, capture, and the win", 2)
    veil(slide, 8.20, 1.72, 4.50, 5.05)
    item(slide, "01", "Place one orb", ["An empty cell, or a cell", "you already own."], 0.70, 1.84, 6.9)
    item(slide, "02", "Explode at critical mass", ["Corner 2, edge 3,", "interior cell 4."], 0.70, 3.10, 6.9)
    item(slide, "03", "Capture the neighbours", ["One orb enters each orthogonal", "neighbour and takes the cell."], 0.70, 4.36, 6.9)
    item(slide, "04", "Last colour standing", ["A colour with no orbs is out", "after everyone has entered."], 0.70, 5.62, 6.9)
    rule(slide, 8.05, 1.84, 4.85, vertical=True)
    text(slide, "EXPLOSION THRESHOLDS", 8.45, 1.84, 4.20, 0.28, 13, TEAL, True)
    text(slide, "2", 8.45, 2.40, 0.70, 0.62, 40, GREEN, True)
    text(slide, "Corner cell", 9.30, 2.42, 3.30, 0.36, 20, WHITE, True)
    text(slide, "Two neighbours", 9.30, 2.82, 3.30, 0.30, 16, BODY)
    rule(slide, 8.45, 3.32, 4.15)
    text(slide, "3", 8.45, 3.52, 0.70, 0.62, 40, GREEN, True)
    text(slide, "Edge cell", 9.30, 3.54, 3.30, 0.36, 20, WHITE, True)
    text(slide, "Three neighbours", 9.30, 3.94, 3.30, 0.30, 16, BODY)
    rule(slide, 8.45, 4.44, 4.15)
    text(slide, "4", 8.45, 4.64, 0.70, 0.62, 40, GREEN, True)
    text(slide, "Interior cell", 9.30, 4.66, 3.30, 0.36, 20, WHITE, True)
    text(slide, "Four neighbours", 9.30, 5.06, 3.30, 0.30, 16, BODY)
    text(slide, "The chain continues until no cell is still critical.", 8.45, 6.05, 4.20, 0.55, 15, BODY)

    slide = content_slide(prs, "THE PROGRAM", "The 9×6 board and each seat", 3)
    frame = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.70), Inches(1.78), Inches(7.35), Inches(4.95))
    paint(frame, FRAME, line=LINE)
    slide.shapes.add_picture(str(FIG / "screen-seated.png"), Inches(0.82), Inches(1.90), Inches(7.11))
    veil(slide, 8.28, 1.72, 4.42, 5.05)
    item(slide, "01", "Default board", ["6 columns by 9 rows.", "Move cap is off."], 8.55, 1.84, 4.15)
    item(slide, "02", "Human or AI", ["Click P1 · HUMAN to cycle", "that seat through the agents."], 8.55, 3.20, 4.15)
    item(slide, "03", "Same clock", ["Each agent gets 0.22 seconds", "and returns one legal cell."], 8.55, 4.56, 4.15)
    text(slide, "The list below the cards seats the player about to move.", 8.55, 6.05, 4.10, 0.60, 14, MUTED)

    slide = content_slide(prs, "THREE AGENTS", "One interface, three searches", 4)
    agents = [
        (0.70, RED, "A1", ["Minimax +", "alpha-beta"], "ADVERSARIAL SEARCH", ["Looks ahead, orders", "explosions first, and", "cuts hopeless replies."], ["Both rivals share", "the min side."]),
        (4.76, BLUE, "A2", ["Monte Carlo", "Tree Search"], "SIMULATION-BASED SEARCH", ["Samples strong cells", "and plays the child", "visited most often."], ["At most 8 children.", "Rollouts prefer bursts."]),
        (8.82, GREEN, "A3", ["Forward", "checking"], "CONSTRAINT-BASED PLANNING", ["Assigns a move, shrinks", "the next domain, and", "keeps the best worst case."], ["Horizon grows to 4.", "Last finished plan is kept."]),
    ]
    for x, accent, code, title, kind, desc, detail in agents:
        card(slide, x, 1.78, 3.81, 4.85, accent)
        text(slide, code, x + 0.22, 1.96, 3.35, 0.30, 16, accent, True)
        text(slide, title, x + 0.22, 2.40, 3.35, 0.80, 22, WHITE, True)
        text(slide, kind, x + 0.22, 3.32, 3.35, 0.26, 11, accent, True)
        text(slide, desc, x + 0.22, 3.72, 3.35, 1.20, 16, BODY)
        rule(slide, x + 0.22, 5.10, 3.35)
        text(slide, detail, x + 0.22, 5.28, 3.35, 0.70, 15, BODY)

    slide = content_slide(prs, "ONE POSITION", "The centre already holds three red orbs", 5)
    frame = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.70), Inches(1.78), Inches(7.15), Inches(4.95))
    paint(frame, FRAME, line=LINE)
    slide.shapes.add_picture(str(FIG / "scenario-before.png"), Inches(0.82), Inches(1.90), Inches(6.91))
    veil(slide, 8.15, 1.72, 4.55, 5.05)
    item(slide, "01", "3×3, Red to move", ["Every colour has already", "entered the match."], 8.40, 1.84, 4.25)
    item(slide, "02", "Centre is critical next", ["(1, 1) has 3 orbs.", "An interior cell bursts at 4."], 8.40, 3.20, 4.25)
    item(slide, "03", "Corners do not win", ["Up and right are blue.", "Left and down are green."], 8.40, 4.56, 4.25)
    text(slide, "Playing the centre ends the game at once.", 8.40, 6.10, 4.20, 0.50, 15, GREEN, True)

    slide = content_slide(prs, "MOVE ORDER", "Five legal cells, tried in this order", 6)
    steps = [
        ("01", "(1, 1) first", "It is Red’s cell, and 3 + 1 meets the interior critical mass of 4."),
        ("02", "Then the corners", "None of them explode. Count is 0, so row order is kept."),
        ("03", "The list", "(0, 0), then (0, 2), then (2, 0), then (2, 2)."),
        ("04", "Enemy cells are absent", "Blue and Green cells are not legal for Red."),
        ("05", "Why the order matters", "The win is generated before any corner, so later cuts have a bound."),
        ("06", "Same list, three agents", "Minimax, MCTS and forward checking all call ordered()."),
    ]
    veil(slide, 6.75, 1.68, 5.95, 5.10)
    for index, (number, heading, body) in enumerate(steps):
        item(slide, number, heading, [body], 0.70 + (index % 2) * 6.30, 1.78 + (index // 2) * 1.65, 5.90)

    slide = content_slide(prs, "THE WIN", "What playing the centre does", 7)
    steps = [
        ("01", "3 becomes 4", "The centre meets its critical mass and is queued."),
        ("02", "One burst", "The cell is cleared. One orb goes to each neighbour."),
        ("03", "Four captures", "(0, 1) and (1, 2) were blue. (1, 0) and (2, 1) were green."),
        ("04", "Each becomes red 2", "An edge explodes at 3, so the chain stops."),
        ("05", "Both opponents are out", "Red has 8 orbs on 4 cells. Blue and Green have none."),
        ("06", "Utility is 1", "The child is terminal. There is no reply to search."),
    ]
    veil(slide, 6.75, 1.68, 5.95, 5.10)
    for index, (number, heading, body) in enumerate(steps):
        item(slide, number, heading, [body], 0.70 + (index % 2) * 6.30, 1.78 + (index // 2) * 1.65, 5.90)

    slide = content_slide(prs, "HEURISTIC", "After Red plays the corner (0, 0)", 8)
    text(slide, "A win is 1. A loss is −1. An open board stays between the two.", 0.70, 1.68, 7.2, 0.32, 16, BODY)
    veil(slide, 8.15, 2.00, 4.55, 4.70)
    rows = [
        ("01", "(0, 0)  Red", "Count 1, critical 2, threat. Weight 4, signed +4."),
        ("02", "(1, 1)  Red", "Count 3, critical 4, threat. Weight 6, signed +6."),
        ("03", "Four enemy cells", "Each weight 1. Signed −1, four times."),
    ]
    for index, (number, heading, body) in enumerate(rows):
        y = 2.15 + index * 0.95
        text(slide, number, 0.70, y, 0.50, 0.28, 14, GREEN, True)
        text(slide, heading, 1.30, y - 0.02, 6.20, 0.34, 20, WHITE, True)
        text(slide, body, 1.30, y + 0.36, 6.20, 0.36, 16, BODY)
    rule(slide, 8.05, 2.15, 4.50, vertical=True)
    text(slide, "6", 8.40, 2.15, 1.40, 0.70, 44, GREEN, True)
    text(slide, "/  42   =   0.1429", 9.70, 2.38, 2.90, 0.40, 18, WHITE, True)
    text(slide, "Score +4+6−1−1−1−1. The limit is the sum of critical mass + 2 over every cell.", 8.40, 3.05, 4.20, 0.85, 15, BODY)
    rule(slide, 8.40, 4.10, 4.20)
    text(slide, "2", 8.40, 4.30, 1.40, 0.70, 44, BLUE, True)
    text(slide, "/  42   =   0.0476", 9.70, 4.53, 2.90, 0.40, 18, WHITE, True)
    text(slide, "Blue adds to (0, 1). That cell becomes a threat, so its weight rises from 1 to 5.", 8.40, 5.20, 4.20, 0.80, 15, BODY)

    slide = content_slide(prs, "MINIMAX", "Depth-2 tree on the centre-win position", 9)
    slide.shapes.add_picture(str(FIG / "tree-minimax.png"), Inches(1.97), Inches(1.72), Inches(9.40))

    slide = content_slide(prs, "ALPHA-BETA", "How that tree is walked", 10)
    steps = [
        ("01", "Explosions first", "ordered() puts (1, 1) ahead of every empty corner."),
        ("02", "The centre is terminal", "result() runs the real chain. utility() returns 1."),
        ("03", "Alpha becomes 1", "No later move can beat a proved win."),
        ("04", "First corner reply", "Blue plays (0, 1). min_value returns 0.0476."),
        ("05", "The rest is cut", "Four replies of that corner are never generated."),
        ("06", "Same cut, three times", "(0, 2), (2, 0) and (2, 2) stop after one reply. Play (1, 1)."),
    ]
    veil(slide, 6.75, 1.68, 5.95, 5.10)
    for index, (number, heading, body) in enumerate(steps):
        column = index % 2
        row = index // 2
        item(slide, number, heading, [body], 0.70 + column * 6.30, 1.78 + row * 1.65, 5.90)

    slide = content_slide(prs, "NODES OPENED", "25 successors without pruning, 9 with it", 11)
    veil(slide, 6.75, 1.68, 5.95, 5.10)
    item(slide, "01", "Alpha starts at −∞", "The centre returns 1. Alpha becomes 1. Beta stays +∞.", 0.70, 1.78, 5.90)
    item(slide, "02", "First corner", "(0, 0) then Blue (0, 1) scores 0.0476, which is ≤ alpha.", 7.00, 1.78, 5.90)
    item(slide, "03", "Cut", "The other four replies of that corner are not generated.", 0.70, 3.43, 5.90)
    item(slide, "04", "Three more cuts", "(0, 2), (2, 0) and (2, 2) each open only (0, 1).", 7.00, 3.43, 5.90)
    item(slide, "05", "16 replies never built", "A full depth-2 tree has 5 root moves and 20 replies.", 0.70, 5.08, 5.90)
    item(slide, "06", "The move", "9 calls to result(). The saved action stays (1, 1).", 7.00, 5.08, 5.90)

    slide = content_slide(prs, "MCTS", "Forty iterations, seed 1", 12)
    slide.shapes.add_picture(str(FIG / "tree-mcts.png"), Inches(1.97), Inches(1.72), Inches(9.40))

    slide = content_slide(prs, "ONE ITERATION", "Select, expand, simulate, back up", 13)
    steps = [
        ("01", "Selection", "High UCB on our turn. Low UCB on an opponent turn."),
        ("02", "The formula", "Average + 1.41 × sqrt( ln(parent visits) / visits )."),
        ("03", "Expansion", "The next unused strong move. A node keeps at most 8 children."),
        ("04", "Simulation", "At most 6 further plies, preferring a cell that explodes."),
        ("05", "Backup", "Add utility() to every node on the path and count the visit."),
        ("06", "The move", "Most visits wins. A match runs this loop for 0.22 seconds."),
    ]
    veil(slide, 6.75, 1.68, 5.95, 5.10)
    for index, (number, heading, body) in enumerate(steps):
        column = index % 2
        row = index // 2
        item(slide, number, heading, [body], 0.70 + column * 6.30, 1.78 + row * 1.65, 5.90)

    slide = content_slide(prs, "ITERATIONS 1–5", "The five children, then the walk returns", 14)
    veil(slide, 6.75, 1.68, 5.95, 5.10)
    rows = [
        ("01", "(1, 1)", "Terminal. Prior 1. Rollout +1."),
        ("02", "(0, 0)", "Prior 0.1429. Rollout +1."),
        ("03", "(0, 2)", "Prior 0.1429. Rollout −1."),
        ("04", "(2, 0)", "Prior 0.1429. Rollout +1."),
        ("05", "(2, 2)", "Prior 0.1429. Rollout −1."),
        ("06", "Back to (1, 1)", "UCB 2.26 against 1.84 and 0.84."),
    ]
    for index, (number, heading, body) in enumerate(rows):
        item(slide, number, heading, [body], 0.70 + (index % 2) * 6.30, 1.78 + (index // 2) * 1.65, 5.90)

    slide = content_slide(prs, "THE DECISION", "Most visits, not the highest final UCB", 15)
    veil(slide, 6.75, 1.68, 5.95, 5.10)
    rows = [
        ("01", "(1, 1)  ·  29 visits", "Mean 1.00. UCB 1.50. Chosen."),
        ("02", "(0, 2) and (2, 2)", "2 visits, mean −0.43, UCB 1.49."),
        ("03", "(2, 0)  ·  8 visits", "Mean 0.39. UCB 1.35."),
        ("04", "(0, 0)  ·  4 visits", "Mean −0.21. UCB 1.14."),
        ("05", "28 of 40 iterations", "Selection returns to the centre after the tree is full."),
        ("06", "Root total is 28", "34 rollouts are +1 and 6 are −1. 34 − 6 = 28."),
    ]
    for index, (number, heading, body) in enumerate(rows):
        item(slide, number, heading, [body], 0.70 + (index % 2) * 6.30, 1.78 + (index // 2) * 1.65, 5.90)

    slide = content_slide(prs, "FORWARD CHECKING", "The same position, scored as a plan", 16)
    steps = [
        ("01", "Horizon 1", "(1, 1) is terminal. Score 1. The bound becomes 1."),
        ("02", "A corner at horizon 1", "The heuristic is 0.1429. It does not replace the centre."),
        ("03", "Horizon 2, centre first", "Still terminal, so it has no replies. The bound stays 1."),
        ("04", "Blue’s first reply", "(0, 1) scores 0.0476, which cannot beat the bound."),
        ("05", "The line stops", "The other four replies of that corner are not assigned."),
        ("06", "The saved move", "The same cut hits every corner. choose_move returns (1, 1)."),
    ]
    veil(slide, 6.75, 1.68, 5.95, 5.10)
    for index, (number, heading, body) in enumerate(steps):
        column = index % 2
        row = index // 2
        item(slide, number, heading, [body], 0.70 + column * 6.30, 1.78 + row * 1.65, 5.90)

    slide = content_slide(prs, "FROM THE LAB", "What changed for this board", 17)
    steps = [
        ("01", "Three players", "The mover maximises. The other two seats share the min side."),
        ("02", "Real rules", "result() runs the chain reaction instead of writing X or O."),
        ("03", "A 0.22-second clock", "Alpha-beta, ordering, and iterative deepening. Finished depth is 3."),
        ("04", "A narrower tree", "MCTS keeps 8 children and biases rollouts toward explosions."),
        ("05", "Not the first solution", "Every opening move is scored. A line worse than the bound is pruned."),
        ("06", "No board copy", "State is immutable, so result() applies the move on a new state."),
    ]
    veil(slide, 6.75, 1.68, 5.95, 5.10)
    for index, (number, heading, body) in enumerate(steps):
        column = index % 2
        row = index // 2
        item(slide, number, heading, [body], 0.70 + column * 6.30, 1.78 + row * 1.65, 5.90)

    slide = content_slide(prs, "GAMEPLAY", "Sped-up match on the default board", 18)
    text(slide, "Red is Minimax. Blue is MCTS. Green is forward checking.", 0.70, 1.62, 8.2, 0.32, 16, BODY)
    poster = FIG / "match-move-48.png"
    movie = ROOT / "Chain-Reaction-Gameplay-9x6.mp4"
    slide.shapes.add_movie(
        str(movie), Inches(2.99), Inches(2.10), Inches(7.36), Inches(4.70),
        poster_frame_image=str(poster), mime_type="video/mp4",
    )

    slide = content_slide(prs, "TWELVE GAMES", "Same 9×6 board, all six seat orders, twice", 19)
    columns = [
        (0.70, RED, "A1", "Minimax", "7 / 12", [("Time", "219 ms"), ("Positions", "7,100"), ("Per second", "32,700"), ("Finishes", "depth 3")]),
        (4.76, BLUE, "A2", "MCTS", "3 / 12", [("Time", "216 ms"), ("Positions", "4,800"), ("Per second", "22,400"), ("Finishes", "8 cells, revisited")]),
        (8.82, GREEN, "A3", "Forward check", "2 / 12", [("Time", "219 ms"), ("Positions", "8,800"), ("Per second", "40,100"), ("Finishes", "horizon 3")]),
    ]
    for x, accent, code, name, wins, stats in columns:
        card(slide, x, 1.78, 3.81, 4.55, accent)
        text(slide, code, x + 0.22, 1.96, 1.20, 0.28, 15, accent, True)
        text(slide, name, x + 0.22, 2.32, 3.35, 0.36, 22, WHITE, True)
        text(slide, wins, x + 0.22, 2.82, 3.35, 0.55, 32, GREEN, True)
        text(slide, "WINS", x + 2.15, 3.00, 1.30, 0.28, 13, MUTED, True)
        for index, (label, value) in enumerate(stats):
            y = 3.55 + index * 0.58
            text(slide, label, x + 0.22, y, 1.55, 0.30, 14, MUTED)
            text(slide, value, x + 1.70, y, 1.85, 0.30, 16, WHITE, True, PP_ALIGN.RIGHT)
    text(slide, "A position is a trial board from result(). The live board stays unchanged.", 0.70, 6.48, 7.6, 0.32, 14, MUTED)

    slide = content_slide(prs, "ONE MATCH", "The recording is not the study", 20)
    frame = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.70), Inches(1.78), Inches(7.35), Inches(4.95))
    paint(frame, FRAME, line=LINE)
    slide.shapes.add_picture(str(FIG / "match-final.png"), Inches(0.82), Inches(1.90), Inches(7.11))
    veil(slide, 8.28, 1.72, 4.42, 5.05)
    item(slide, "01", "This recording", ["Red, playing Minimax,", "won after 97 moves."], 8.55, 1.84, 4.15)
    item(slide, "02", "Twelve games", ["Minimax 7, MCTS 3,", "forward checking 2."], 8.55, 3.20, 4.15)
    item(slide, "03", "Legal and on time", ["No illegal cell.", "No turn past the clock."], 8.55, 4.56, 4.15)
    text(slide, "One opening does not decide the comparison.", 8.55, 6.10, 4.10, 0.45, 15, BODY)

    slide = content_slide(prs, "THE TRACE", "What all three searches agree on", 21)
    text(slide, "All three return (1, 1).", 0.70, 1.85, 11.9, 0.70, 36, WHITE, True)
    text(slide, "The same rules and the same utility, on the centre-win position.", 0.70, 2.65, 11.9, 0.36, 18, BODY)
    rule(slide, 0.70, 3.20, 11.93)
    veil(slide, 6.85, 3.35, 5.85, 2.85)
    item(slide, "01", "Minimax proves it", "The centre returns 1. Every corner is cut at 0.0476.", 0.70, 3.50, 6.0)
    item(slide, "02", "MCTS samples it", "29 visits, mean 1.00. The next child has 8 visits.", 0.70, 4.85, 6.0)
    item(slide, "03", "The planner bounds it", "Bound becomes 1, so every corner is pruned.", 7.05, 3.50, 5.5)
    item(slide, "04", "On the long board", "The finished 3-ply minimax search wins most often.", 7.05, 4.85, 5.5)

    prs.save(OUT)
    print(OUT)


if __name__ == "__main__":
    build()
