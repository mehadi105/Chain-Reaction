import math
import time

from ..engine import Status, apply_move, critical_mass

# Set by minimax() before the search. Chain Reaction has three players, so the
# seat about to move is the maximizer and the other two seats share the min side.
_maximizer = 0
_deadline = math.inf
_cutoff = False


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


def ordered(state):
    """Explosions first, then fuller cells, so alpha-beta can cut sooner."""
    config = state.config
    me = player(state)

    def key(action):
        cell = state.cell(action[0], action[1])
        explodes = cell.owner == me and cell.count + 1 >= critical_mass(config, action[0], action[1])
        return (explodes, cell.count)

    return sorted(actions(state), key=key, reverse=True)


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


def out_of_time():
    global _cutoff
    if time.monotonic() > _deadline:
        _cutoff = True
        return True
    return False


def max_value(state, alpha, beta, depth):
    if terminal(state) or depth == 0 or out_of_time():
        return utility(state)

    value = -math.inf

    for action in ordered(state):
        if out_of_time():
            break
        new_state = result(state, action)
        eval_value = next_value(new_state, alpha, beta, depth - 1)

        if eval_value > value:
            value = eval_value
        if value >= beta:
            return value
        if value > alpha:
            alpha = value

    if value == -math.inf:
        return utility(state)
    return value


def min_value(state, alpha, beta, depth):
    if terminal(state) or depth == 0 or out_of_time():
        return utility(state)

    value = math.inf

    for action in ordered(state):
        if out_of_time():
            break
        new_state = result(state, action)
        eval_value = next_value(new_state, alpha, beta, depth - 1)

        if eval_value < value:
            value = eval_value
        if value <= alpha:
            return value
        if value < beta:
            beta = value

    if value == math.inf:
        return utility(state)
    return value


def next_value(state, alpha, beta, depth):
    if player(state) == _maximizer:
        return max_value(state, alpha, beta, depth)
    return min_value(state, alpha, beta, depth)


def minimax(state, depth=2):
    global _maximizer, _cutoff
    _maximizer = player(state)
    _cutoff = False
    best_action = None

    if player(state) == _maximizer:
        best_value = -math.inf
        alpha = -math.inf
        beta = math.inf

        for action in ordered(state):
            if out_of_time():
                break
            new_state = result(state, action)
            value = next_value(new_state, alpha, beta, depth - 1)

            if value > best_value:
                best_value = value
                best_action = action
            if best_value > alpha:
                alpha = best_value

    else:
        best_value = math.inf
        alpha = -math.inf
        beta = math.inf

        for action in ordered(state):
            if out_of_time():
                break
            new_state = result(state, action)
            value = next_value(new_state, alpha, beta, depth - 1)

            if value < best_value:
                best_value = value
                best_action = action
            if best_value < beta:
                beta = best_value

    if best_action is None:
        moves = actions(state)
        if not moves:
            raise ValueError("No legal move")
        return moves[0]
    return best_action


class MinimaxAgent:
    name = "Minimax + alpha-beta"

    def __init__(self, depth=6):
        self.depth = depth

    def choose_move(self, state, deadline):
        global _deadline
        moves = ordered(state)
        if not moves:
            raise ValueError("No legal move")
        if time.monotonic() >= deadline:
            return moves[0]
        _deadline = deadline
        # Deepen until the budget runs out, and keep the last depth that finished.
        best = moves[0]
        for depth in range(1, self.depth + 1):
            if time.monotonic() >= _deadline:
                break
            move = minimax(state, depth)
            if _cutoff:
                break
            best = move
        return best
