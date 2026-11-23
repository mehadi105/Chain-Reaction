"""Capture the evaluation scenario, screenshots, and a sped-up match."""
from __future__ import annotations
import json
import math
import random
from pathlib import Path

from chain_reaction.agents import cpsat as cp
from chain_reaction.agents import mcts as mc
from chain_reaction.agents import minimax as mm
from chain_reaction.controller import Controller
from chain_reaction.engine import (
    Cell, Config, EMPTY, State, Status, apply_move, critical_mass,
)
from chain_reaction.render import Renderer

OUT = Path(__file__).resolve().parent
FIG = OUT / "figures"
FIG.mkdir(exist_ok=True)


def winning_state() -> State:
    board = [EMPTY] * 9
    board[4] = Cell(0, 3)
    board[1] = Cell(1, 1)
    board[3] = Cell(2, 1)
    board[5] = Cell(1, 1)
    board[7] = Cell(2, 1)
    return State(
        Config(rows=3, cols=3), tuple(board), 0, (1, 1, 1),
        frozenset(), 3, Status.PLAYING,
    )


def cell_rows(state: State) -> list[str]:
    rows = []
    for r in range(state.config.rows):
        bits = []
        for c in range(state.config.cols):
            cell = state.cell(r, c)
            if not cell.count:
                bits.append(" . ")
            else:
                bits.append(f"{'RBG'[cell.owner]}{cell.count}")
        rows.append(" ".join(bits))
    return rows


def heuristic_parts(state: State, maximizer: int) -> dict:
    config = state.config
    rows = []
    score = 0
    limit = 0
    for index, cell in enumerate(state.board):
        row, col = divmod(index, config.cols)
        crit = critical_mass(config, row, col)
        limit += crit + 2
        if not cell.count:
            continue
        threat = cell.count >= crit - 1
        weight = cell.count + (3 if threat else 0)
        sign = 1 if cell.owner == maximizer else -1
        score += sign * weight
        rows.append({
            "cell": [row, col],
            "owner": cell.owner,
            "count": cell.count,
            "critical": crit,
            "threat": threat,
            "weight": weight,
            "signed": sign * weight,
        })
    value = 0 if limit == 0 else max(-0.99, min(0.99, score / limit))
    return {"parts": rows, "score": score, "limit": limit, "value": round(value, 4)}


def trace_minimax(state: State) -> dict:
    mm._maximizer = 0
    mm._deadline = math.inf
    mm._cutoff = False
    root_moves = []
    for action in mm.ordered(state):
        child = mm.result(state, action)
        if mm.terminal(child):
            value = mm.utility(child)
            root_moves.append({
                "move": list(action),
                "terminal": True,
                "winner": child.winner,
                "value": value,
                "replies": [],
                "pruned_after": None,
            })
            continue
        replies = []
        for reply in mm.ordered(child):
            nxt = mm.result(child, reply)
            replies.append({
                "move": list(reply),
                "value": round(mm.utility(nxt), 4),
                "terminal": mm.terminal(nxt),
                "winner": nxt.winner,
                "board": cell_rows(nxt),
            })
        value = min(item["value"] for item in replies)
        root_moves.append({
            "move": list(action),
            "terminal": False,
            "winner": None,
            "value": round(value, 4),
            "replies": replies,
            "board": cell_rows(child),
        })
    # Alpha-beta with explosions ordered first: winning move is first.
    # After it returns 1, alpha is 1, so each later min-node cuts off
    # at the first reply whose value is <= 1 (every finite reply).
    expanded = []
    for index, item in enumerate(root_moves):
        if index == 0:
            expanded.append({**item, "alpha_beta": "fully scored, sets alpha = 1"})
        else:
            first = item["replies"][0] if item["replies"] else None
            expanded.append({
                "move": item["move"],
                "value_if_fully_searched": item["value"],
                "alpha_beta": "cut off after the first reply",
                "first_reply": None if first is None else {
                    "move": first["move"],
                    "value": first["value"],
                },
                "replies_not_opened": max(0, len(item["replies"]) - 1),
            })
    return {"order": [item["move"] for item in root_moves], "full": root_moves, "alpha_beta": expanded}


def trace_mcts(state: State, iterations: int = 40) -> dict:
    random.seed(1)
    mc._maximizer = mm.player(state)
    mc._deadline = math.inf
    mc._rollout_depth = 4
    root = mc.MCTSNode(state)
    for _ in range(iterations):
        node = mc.selection(root)
        node = mc.expansion(node)
        value = mc.simulation(node)
        mc.backpropagation(node, value)
    children = []
    for child in root.children:
        children.append({
            "move": list(child.action),
            "visits": child.visits,
            "mean": round(child.total_value / child.visits, 4),
            "total": round(child.total_value, 4),
        })
    chosen = max(root.children, key=lambda child: child.visits)
    return {
        "iterations": iterations,
        "rollout_depth": 4,
        "seed": 1,
        "children": children,
        "chosen": list(chosen.action),
    }


def trace_cpsat(state: State) -> dict:
    cp._maximizer = 0
    first_moves = []
    for move in cp.ordered(state):
        nxt = cp.result(state, move)
        if cp.terminal(nxt):
            first_moves.append({
                "move": list(move),
                "terminal": True,
                "worst": cp.utility(nxt),
                "replies": [],
            })
            continue
        replies = []
        for reply in cp.ordered(nxt):
            after = cp.result(nxt, reply)
            replies.append({"move": list(reply), "value": round(cp.utility(after), 4)})
        worst = min(item["value"] for item in replies)
        first_moves.append({
            "move": list(move),
            "terminal": False,
            "worst": round(worst, 4),
            "best_reply_for_us": max(item["value"] for item in replies),
            "replies": replies,
        })
    chosen = max(first_moves, key=lambda item: item["worst"])
    return {"horizon": 2, "moves": first_moves, "chosen": chosen["move"]}


def save_ui(name: str, model: Controller) -> None:
    Renderer().render(model).save(FIG / name)


def scenario_frames(state: State) -> None:
    model = Controller(state.config)
    model.storage_enabled = False
    model.session.state = state
    model.started = True
    model.show_counts = True
    model.seats = ["Minimax + alpha-beta", "MCTS", "CP-SAT planner"]
    model.notify("Red to move. The centre cell is one orb from exploding.")
    save_ui("scenario-before.png", model)
    model.place(1, 1)
    # Fast animation: a few frames of the burst, then the finished win.
    model.speed = 2
    renderer = Renderer()
    for index, dt in enumerate((0.04, 0.08, 0.08, 0.2, 0.2)):
        model.update(dt)
        renderer.render(model).save(FIG / f"scenario-burst-{index}.png")
    while model.busy:
        model.update(0.2)
    renderer.render(model).save(FIG / "scenario-after.png")


def menu_frames() -> None:
    model = Controller(Config(rows=9, cols=6))
    model.storage_enabled = False
    save_ui("screen-start.png", model)
    model.action("startpause")
    model.seats = ["Minimax + alpha-beta", "MCTS", "CP-SAT planner"]
    model.notify("Red: Minimax.  Blue: MCTS.  Green: CP-SAT.")
    save_ui("screen-seated.png", model)
    model.action("help")
    save_ui("screen-help.png", model)


def record_match() -> dict:
    frames = FIG / "frames"
    frames.mkdir(exist_ok=True)
    model = Controller(Config(rows=9, cols=6))
    model.storage_enabled = False
    model.speed = 2
    model.show_counts = True
    model.action("startpause")
    model.seats = ["Minimax + alpha-beta", "MCTS", "CP-SAT planner"]
    model.notify("9×6 board. Red: Minimax. Blue: MCTS. Green: CP-SAT.")
    renderer = Renderer()
    saved = 0

    def snap() -> None:
        nonlocal saved
        renderer.render(model).save(frames / f"frame_{saved:04d}.png")
        saved += 1

    for _ in range(12):
        snap()
    guard = 0
    while model.state.status is Status.PLAYING and model.state.move_number < 140 and guard < 12000:
        guard += 1
        before = model.state.move_number
        model.update(0.05)
        if guard % 2 == 0:
            snap()
        if model.state.move_number != before and model.state.move_number % 8 == 0:
            renderer.render(model).save(FIG / f"match-move-{model.state.move_number:02d}.png")
            print(f"move {model.state.move_number}", flush=True)
    renderer.render(model).save(FIG / "match-final.png")
    for _ in range(14):
        snap()
    return {
        "moves": model.state.move_number,
        "status": model.state.status.value,
        "winner": None if model.state.winner is None else ["Red", "Blue", "Green"][model.state.winner],
        "frames": saved,
        "counts": [list(pair) for pair in model.state.counts()],
    }


def main() -> None:
    state = winning_state()
    corner = mm.result(state, (0, 0))
    data = {
        "board_before": cell_rows(state),
        "heuristic_corner": heuristic_parts(corner, 0),
        "minimax": trace_minimax(state),
        "mcts": trace_mcts(state),
        "cpsat": trace_cpsat(state),
    }
    menu_frames()
    scenario_frames(state)
    data["match"] = record_match()
    (OUT / "eval_data.json").write_text(json.dumps(data, indent=2))
    print(json.dumps({
        "minimax_choice_values": [
            {"move": item["move"], "value": item["value"]} for item in data["minimax"]["full"]
        ],
        "mcts": data["mcts"],
        "cpsat_worst": [
            {"move": item["move"], "worst": item["worst"]} for item in data["cpsat"]["moves"]
        ],
        "corner_heuristic": data["heuristic_corner"],
        "match": data["match"],
    }, indent=2))


if __name__ == "__main__":
    main()
