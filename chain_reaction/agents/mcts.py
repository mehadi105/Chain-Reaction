import math
import random
import time

from ..engine import Status, apply_move, critical_mass

# Utility is scored for this seat. That seat selects the max UCB child;
# the other seats select the min UCB child, matching the lab's X / O split.
_maximizer = 0
_deadline = math.inf
_rollout_depth = 10


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


def explodes(state, action):
    cell = state.cell(action[0], action[1])
    return cell.owner == player(state) and cell.count + 1 >= critical_mass(state.config, action[0], action[1])


class MCTSNode:
    def _init_(self, state, parent=None, action=None):
        self.state = state
        self.parent = parent
        self.action = action
        self.children = []
        self.visits = 0
        self.total_value = 0
        self.untried_actions = ordered(state)


def ucb1(node, C=1.41):
    if node.visits == 0:
        return math.inf
    exploitation = node.total_value / node.visits
    exploration = (C * math.sqrt(math.log(node.parent.visits) / node.visits))
    return exploitation + exploration


def selection(node):
    while not terminal(node.state):
        # Keep the tree narrow so the budget revisits strong moves instead of
        # spending one visit on every legal cell.
        if len(node.untried_actions) > 0 and len(node.children) < 8:
            return node
        if len(node.children) == 0:
            return node
        if player(node.state) == _maximizer:
            best_child = max(node.children, key=ucb1)
        else:
            best_child = min(node.children, key=ucb1)
        node = best_child
    return node


def expansion(node):
    if terminal(node.state) or len(node.untried_actions) == 0:
        return node
    action = node.untried_actions.pop(0)
    new_state = result(node.state, action)
    child = MCTSNode(state=new_state, parent=node, action=action)
    child.visits = 1
    child.total_value = utility(new_state)
    node.children.append(child)
    return child


def simulation(node):
    current_state = node.state
    steps = 0
    while not terminal(current_state) and steps < _rollout_depth:
        if time.monotonic() > _deadline:
            break
        possible_actions = actions(current_state)
        if not possible_actions:
            break
        explosive = [action for action in possible_actions if explodes(current_state, action)]
        random_action = random.choice(explosive or possible_actions)
        current_state = result(current_state, random_action)
        steps += 1
    return utility(current_state)


def backpropagation(node, result_value):
    while node is not None:
        node.visits += 1
        node.total_value += result_value
        node = node.parent


def mcts(state, iterations=100):
    global _maximizer
    _maximizer = player(state)
    root = MCTSNode(state)
    for i in range(iterations):
        if time.monotonic() > _deadline:
            break
        node = selection(root)
        node = expansion(node)
        result_value = simulation(node)
        backpropagation(node, result_value)

    if len(root.children) == 0:
        moves = actions(state)
        if not moves:
            raise ValueError("No legal move")
        return moves[0]
    best_child = max(root.children, key=lambda child: child.visits)
    return best_child.action


class MCTSAgent:
    name = "MCTS"

    def _init_(self, seed=None, rollout_depth=6, iterations=10000):
        self.seed = seed
        self.rollout_depth = rollout_depth
        self.iterations = iterations

    def choose_move(self, state, deadline):
        global _deadline, _rollout_depth
        moves = actions(state)
        if not moves:
            raise ValueError("No legal move")
        if time.monotonic() >= deadline:
            return moves[0]
        if self.seed is not None:
            random.seed(self.seed)
        _deadline = deadline
        _rollout_depth = self.rollout_depth
        return mcts(state, self.iterations)