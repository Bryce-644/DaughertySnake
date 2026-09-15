# Battlesnake — "Daugherty"
#
# All decision logic lives in this file. server.py is the unmodified starter
# Flask shim and should not need changes.
#
# Board coordinates: (0, 0) is the bottom-left square, "up" increases y.
#
# Each turn every candidate move is scored and the best one wins:
#
#   1. Hard safety  -- never leave the board, never enter a square that will
#                      still be occupied when we arrive.
#   2. Space        -- flood fill from each candidate so we never seal ourselves
#                      into a pocket smaller than our own body.
#   3. Food         -- distance to nearest reachable food, weighted by health.
#   4. Head to head -- dodge squares a longer snake could take, lean into
#                      squares only a shorter snake could take.

import typing
from collections import deque

Cell = typing.Tuple[int, int]

DIRECTIONS: typing.Dict[str, Cell] = {
    "up": (0, 1),
    "down": (0, -1),
    "left": (-1, 0),
    "right": (1, 0),
}

# --- Tuning knobs -----------------------------------------------------------
# These are the numbers to adjust between tournament rounds.

W_SPACE = 2.0              # per reachable square
W_TRAP_BASE = -250.0       # flat penalty for entering a pocket we do not fit in
W_TRAP_PER_CELL = -30.0    # extra penalty per square we come up short
W_H2H_LOSS = -400.0        # square a same-length-or-longer snake could also take
W_H2H_WIN = 60.0           # square only a shorter snake could take (we win it)
W_ENEMY_HEAD_NEAR = -6.0   # mild aversion to loitering beside bigger snakes
W_HAZARD = -25.0           # hazard squares drain health
W_CENTER = -0.6            # per square of distance from board centre
W_NO_FOOD_REACHABLE = -60.0

HUNGRY_HEALTH = 30
PECKISH_HEALTH = 60


def info() -> typing.Dict:
    """GET / — appearance and API version.

    The tournament display name is set on battlesnake.com, not here, and must
    contain "Daugherty" per the event rules.
    """
    return {
        "apiversion": "1",
        "author": "Daugherty",
        "color": "#22CE83",
        "head": "evil",
        "tail": "bolt",
        "version": "1.0.0",
    }


def start(game_state: typing.Dict):
    print(f"GAME START {game_state['game']['id']}")


def end(game_state: typing.Dict):
    print(f"GAME OVER after {game_state['turn']} turns")


# --- Board helpers ----------------------------------------------------------


def as_cell(point: typing.Dict) -> Cell:
    return point["x"], point["y"]


def neighbors(cell: Cell) -> typing.Iterator[Cell]:
    x, y = cell
    for dx, dy in DIRECTIONS.values():
        yield x + dx, y + dy


def in_bounds(cell: Cell, width: int, height: int) -> bool:
    x, y = cell
    return 0 <= x < width and 0 <= y < height


def may_grow(snake: typing.Dict, food: typing.Set[Cell]) -> bool:
    """True if this snake might be about to eat.

    A growing snake does not free up its tail square, so any conclusion we draw
    about that square has to be a turn more pessimistic.
    """
    return any(nb in food for nb in neighbors(as_cell(snake["head"])))


def add_snake_occupancy(
    free_at: typing.Dict[Cell, int],
    snake: typing.Dict,
    delay: int,
) -> typing.Dict[Cell, int]:
    """Fold one snake's body into a vacate-time map, mutating and returning it.

    A segment `i` squares back from the head of an `n` long snake is vacated
    after `n - i` turns, because the tail has to travel through it first. That
    is what makes entering our own tail square legal, and lets the snake chase
    its tail down a one-wide corridor. `delay` shifts everything a turn later
    for a snake that is about to grow. Squares listed twice (a snake that just
    ate has a doubled tail) keep the later of the two times.
    """
    body = [as_cell(p) for p in snake["body"]]
    length = len(body)
    for index, cell in enumerate(body):
        vacates = length - index + delay
        if vacates > free_at.get(cell, 0):
            free_at[cell] = vacates
    return free_at


def build_free_at(
    snakes: typing.List[typing.Dict],
    food: typing.Set[Cell],
) -> typing.Dict[Cell, int]:
    """Vacate-time map for a set of snakes, assuming any of them may be eating.

    Used for opponents, whose moves we cannot know. Our own body is folded in
    separately per candidate move, because we do know whether *we* are eating.
    """
    free_at: typing.Dict[Cell, int] = {}
    for snake in snakes:
        add_snake_occupancy(free_at, snake, 1 if may_grow(snake, food) else 0)
    return free_at


def flood(
    start_cell: Cell,
    free_at: typing.Dict[Cell, int],
    width: int,
    height: int,
    food: typing.Set[Cell],
) -> typing.Tuple[int, typing.Optional[int]]:
    """Time-aware flood fill from start_cell.

    Returns (reachable square count, distance to nearest reachable food) with
    the distance being None when no food can be reached. Distances are turn
    offsets, so start_cell sits at distance 1 — a square only has to be clear
    by the time we actually get there.
    """
    seen: typing.Set[Cell] = {start_cell}
    queue: typing.Deque[typing.Tuple[Cell, int]] = deque([(start_cell, 1)])
    reachable = 0
    food_distance: typing.Optional[int] = None

    while queue:
        cell, distance = queue.popleft()
        reachable += 1
        if food_distance is None and cell in food:
            food_distance = distance
        for nb in neighbors(cell):
            if nb in seen or not in_bounds(nb, width, height):
                continue
            step = distance + 1
            if free_at.get(nb, 0) > step:
                continue
            seen.add(nb)
            queue.append((nb, step))

    return reachable, food_distance


def food_weight(health: int, is_shortest: bool) -> float:
    """How badly we want to close the distance to food this turn."""
    if health <= HUNGRY_HEALTH:
        return 30.0
    if health <= PECKISH_HEALTH:
        return 12.0
    return 8.0 if is_shortest else 4.0


# --- The decision ------------------------------------------------------------


def choose_move(game_state: typing.Dict) -> str:
    """Pick a direction for this turn. Always returns a direction name."""
    board = game_state["board"]
    you = game_state["you"]
    width, height = board["width"], board["height"]

    food = {as_cell(p) for p in board.get("food") or []}
    hazards = {as_cell(p) for p in board.get("hazards") or []}
    snakes = board["snakes"]
    head = as_cell(you["head"])
    my_length = you["length"]
    my_health = you["health"]

    others = [s for s in snakes if s["id"] != you["id"]]
    is_shortest = bool(others) and all(my_length <= s["length"] for s in others)
    hunger = food_weight(my_health, is_shortest)

    # Opponents only. Our own body depends on whether the move we are looking
    # at eats, so it gets folded in per candidate below.
    others_free_at = build_free_at(others, food)

    # Squares each other snake could move into next turn, split by whether a
    # collision there would kill us or them. Losing squares are counted, not
    # just flagged, so a square two big snakes can both reach scores worse than
    # one only a single snake threatens.
    losing_threats: typing.Dict[Cell, int] = {}
    winning_squares: typing.Set[Cell] = set()
    enemy_heads: typing.List[typing.Tuple[Cell, int]] = []
    for snake in others:
        enemy_head = as_cell(snake["head"])
        enemy_heads.append((enemy_head, snake["length"]))
        for nb in neighbors(enemy_head):
            if not in_bounds(nb, width, height):
                continue
            # Compare raw lengths. If the contested square is food then both
            # snakes eat it and both grow by one, so the comparison does not
            # change -- crediting ourselves the +1 here would turn a mutual
            # kill into a phantom win.
            if snake["length"] >= my_length:
                losing_threats[nb] = losing_threats.get(nb, 0) + 1
            else:
                winning_squares.add(nb)

    centre_x, centre_y = (width - 1) / 2, (height - 1) / 2

    scored: typing.List[typing.Tuple[float, str]] = []
    for direction, (dx, dy) in DIRECTIONS.items():
        target = (head[0] + dx, head[1] + dy)

        if not in_bounds(target, width, height):
            continue

        # We know whether this particular move eats, so our own tail timing is
        # exact rather than pessimistic.
        eating = target in food
        free_at = add_snake_occupancy(dict(others_free_at), you, 1 if eating else 0)

        # Must be clear by the time we arrive, one turn from now.
        if free_at.get(target, 0) > 1:
            continue

        reachable, distance_to_food = flood(target, free_at, width, height, food)
        length_after = my_length + (1 if eating else 0)

        score = reachable * W_SPACE

        if reachable < length_after:
            score += W_TRAP_BASE + (length_after - reachable) * W_TRAP_PER_CELL

        if eating:
            score += hunger
        elif distance_to_food is not None:
            score -= hunger * distance_to_food
        elif my_health <= PECKISH_HEALTH:
            score += W_NO_FOOD_REACHABLE

        threats = losing_threats.get(target, 0)
        if threats:
            score += W_H2H_LOSS * threats
        elif target in winning_squares:
            score += W_H2H_WIN

        for enemy_head, enemy_length in enemy_heads:
            if enemy_length >= my_length:
                gap = abs(target[0] - enemy_head[0]) + abs(target[1] - enemy_head[1])
                if gap <= 3:
                    score += W_ENEMY_HEAD_NEAR * (4 - gap)

        if target in hazards:
            score += W_HAZARD

        score += W_CENTER * (abs(target[0] - centre_x) + abs(target[1] - centre_y))

        scored.append((score, direction))

    if not scored:
        # Boxed in with nothing survivable. Take any in-bounds square so we die
        # to a collision rather than forfeiting the game on an invalid move.
        for direction, (dx, dy) in DIRECTIONS.items():
            if in_bounds((head[0] + dx, head[1] + dy), width, height):
                return direction
        return "up"

    # Sort by score, then name, so identical positions always play identically.
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][1]


def move(game_state: typing.Dict) -> typing.Dict:
    """POST /move"""
    return {"move": choose_move(game_state)}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})
