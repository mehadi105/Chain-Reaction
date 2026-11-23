import math
import time

from ..engine import Status, apply_move, critical_mass

# Same role as in the other agents: utility is from the seat that is searching.
_maximizer = 0
_deadline = float("inf")
_root = None


def player(state):
    return state.current_player


def actions(state):
    moves = []
    if state.status is not Status.PLAYING:
        return moves
    for i in range(state.config.rows):
        for j in range(state.config.cols):
            if state.cell(i, j).owner in (-1, state.current_player):
                moves.append((i, j))
    return moves


def ordered(state, moves=None):
    """Try cells that are about to explode before empty cells."""
    if moves is None:
        moves = actions(state)
    config = state.config
    me = player(state)

    def key(move):
        cell = state.cell(move[0], move[1])
        explodes = cell.owner == me and cell.count + 1 >= critical_mass(config, move[0], move[1])
        return (explodes, cell.count)

    return sorted(moves, key=key, reverse=True)


def result(state, action):
    return apply_move(state, action).state


def terminal(state):
    return state.status is not Status.PLAYING


def utility(state):
    if state.status is Status.WON:
        if state.winner == _maximizer:
            return 1
        return -1
    if terminal(state):
        return 0

    config = state.config
    score = 0
    limit = 0
    cols = config.cols
    for index, cell in enumerate(state.board):
        row, col = divmod(index, cols)
        crit = critical_mass(config, row, col)
        limit += crit + 2
        if not cell.count:
            continue
        weight = cell.count + (3 if cell.count >= crit - 1 else 0)
        if cell.owner == _maximizer:
            score += weight
        else:
            score -= weight
    if limit == 0:
        return 0
    value = score / limit
    if value > 0.99:
        return 0.99
    if value < -0.99:
        return -0.99
    return value


def state_after(assignment):
    state = _root
    for ply in range(len(assignment)):
        state = result(state, assignment[ply])
    return state


# Check whether a placement is still legal after the moves already assigned
def is_safe(ply, move, assignment, state=None):
    if state is None:
        state = state_after(assignment)
    if terminal(state):
        return False
    return state.cell(move[0], move[1]).owner in (-1, player(state))


# Forward checking: reduce future domains
def forward_check(ply, move, domains, assignment, state=None):
    new_domains = {}

    # Copy domains so original domains remain unchanged
    for key in domains:
        new_domains[key] = domains[key].copy()

    if assignment.get(ply) != move:
        return None
    if state is None:
        state = state_after(assignment)
    future = ply + 1
    if future not in new_domains:
        return new_domains
    if terminal(state):
        new_domains[future] = []
        return new_domains

    # Keep only columns (moves) that are still legal on the next turn
    new_domains[future] = ordered(state)
    if len(new_domains[future]) == 0:
        return None
    return new_domains


# Recursive backtracking with forward checking.
# A first move is dropped once one reply is already worse than a finished move.
def backtrack_fc(ply, n, assignment, domains, stats, state=None):
    if state is None:
        state = state_after(assignment)
    if ply == n or (ply > 0 and terminal(state)):
        score = utility(state)
        first = assignment[0]
        previous = stats["worst"].get(first)
        if previous is None or score < previous:
            stats["worst"][first] = score
        if ply > 0 and stats["worst"][first] <= stats["bound"]:
            stats["pruned"] = True
        return True

    found = False
    domain = ordered(state, domains.get(ply, [])) if ply == 0 else domains.get(ply, [])
    for move in domain:
        if time.monotonic() > _deadline:
            stats["timed_out"] = True
            break
        if ply == 0:
            stats["pruned"] = False
        stats["attempts"] += 1

        if is_safe(ply, move, assignment, state):
            assignment[ply] = move
            nxt = result(state, move)
            new_domains = forward_check(ply, move, domains, assignment, nxt)

            if new_domains is not None:
                if backtrack_fc(ply + 1, n, assignment, new_domains, stats, nxt):
                    found = True

            # Backtrack
            del assignment[ply]
            stats["backtracks"] += 1

            if stats["timed_out"]:
                break
            if ply == 0:
                worst = stats["worst"].get(move)
                if worst is not None and worst > stats["bound"]:
                    stats["bound"] = worst
                    stats["best_move"] = move
            elif stats["pruned"]:
                break

    return found


def plan(state, n=2):
    global _maximizer, _root
    _maximizer = player(state)
    _root = state
    assignment = {}
    domains = {0: ordered(state)}
    for ply in range(1, n):
        domains[ply] = []

    stats = {
        "attempts": 0,
        "backtracks": 0,
        "worst": {},
        "bound": -math.inf,
        "best_move": None,
        "pruned": False,
        "timed_out": False,
    }
    backtrack_fc(0, n, assignment, domains, stats, state)
    # A proven win stands even when later moves were not reached.
    if stats["bound"] >= 1 and stats["best_move"] is not None:
        return stats["best_move"], True
    if stats["timed_out"] or stats["best_move"] is None:
        fallback = domains[0][0] if domains[0] else None
        return stats["best_move"] or fallback, False
    return stats["best_move"], True


class CPSATAgent:
    name = "CP-SAT planner"

    def __init__(self, horizon=4):
        self.horizon = horizon

    def choose_move(self, state, deadline):
        global _deadline
        moves = ordered(state)
        if not moves:
            raise ValueError("No legal move")
        if time.monotonic() >= deadline:
            return moves[0]
        _deadline = deadline
        best = moves[0]
        for horizon in range(1, self.horizon + 1):
            if time.monotonic() >= _deadline:
                break
            move, done = plan(state, horizon)
            if not done:
                break
            if move is not None:
                best = move
        return best
