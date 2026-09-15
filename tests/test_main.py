import random

import main
from main import DIRECTIONS, build_free_at, choose_move, flood


def pt(x, y):
    return {"x": x, "y": y}


def make_snake(snake_id, cells, health=100):
    body = [pt(x, y) for x, y in cells]
    return {
        "id": snake_id,
        "name": snake_id,
        "health": health,
        "body": body,
        "head": body[0],
        "length": len(body),
        "latency": "1",
        "shout": "",
    }


def make_state(
    me_cells,
    others=(),
    food=(),
    hazards=(),
    health=100,
    width=11,
    height=11,
    turn=10,
):
    me = make_snake("me", me_cells, health)
    snakes = [me] + [
        make_snake(f"opp{i}", cells) for i, cells in enumerate(others)
    ]
    return {
        "game": {"id": "test", "ruleset": {"name": "standard"}, "timeout": 500},
        "turn": turn,
        "board": {
            "width": width,
            "height": height,
            "food": [pt(x, y) for x, y in food],
            "hazards": [pt(x, y) for x, y in hazards],
            "snakes": snakes,
        },
        "you": me,
    }


def target_of(state, direction):
    head = state["you"]["head"]
    dx, dy = DIRECTIONS[direction]
    return head["x"] + dx, head["y"] + dy


# --- Hard safety -------------------------------------------------------------


def test_does_not_move_off_the_board():
    # Head in the bottom-left corner with the neck above it: only "right" is
    # both on the board and not our own neck.
    state = make_state([(0, 0), (0, 1), (0, 2)])
    assert choose_move(state) == "right"


def test_does_not_reverse_into_its_own_neck():
    state = make_state([(5, 5), (5, 6), (5, 7)])
    assert choose_move(state) != "up"


def test_enters_own_tail_square_when_it_is_the_only_option():
    # A 3x3 board with the snake coiled around the edge. The head at (0, 0) has
    # exactly two neighbours on the board: its neck at (1, 0) and its tail at
    # (0, 1). Only the tail square frees up in time.
    coil = [
        (0, 0),  # head
        (1, 0),  # neck
        (2, 0),
        (2, 1),
        (2, 2),
        (1, 2),
        (0, 2),
        (0, 1),  # tail
    ]
    state = make_state(coil, width=3, height=3)
    assert choose_move(state) == "up"


def test_never_returns_an_off_board_move_under_fuzzing():
    rng = random.Random(1234)
    for _ in range(400):
        width = height = 11
        head = (rng.randrange(width), rng.randrange(height))
        body = [head]
        for _ in range(rng.randrange(2, 12)):
            dx, dy = rng.choice(list(DIRECTIONS.values()))
            nxt = (body[-1][0] + dx, body[-1][1] + dy)
            if not main.in_bounds(nxt, width, height) or nxt in body:
                break
            body.append(nxt)
        if len(body) < 2:
            continue
        food = [
            (rng.randrange(width), rng.randrange(height))
            for _ in range(rng.randrange(0, 4))
        ]
        state = make_state(body, food=food, health=rng.randrange(1, 101))
        direction = choose_move(state)
        assert direction in DIRECTIONS
        assert main.in_bounds(target_of(state, direction), width, height)


# --- Occupancy timers --------------------------------------------------------


def test_build_free_at_counts_down_from_the_tail():
    snakes = [make_snake("s", [(1, 1), (1, 2), (1, 3)])]
    free_at = build_free_at(snakes, food=set())
    # Head has to wait for the whole body to pass; the tail clears next turn.
    assert free_at == {(1, 1): 3, (1, 2): 2, (1, 3): 1}


def test_build_free_at_delays_a_snake_that_may_eat():
    snakes = [make_snake("s", [(1, 1), (1, 2), (1, 3)])]
    # Food beside the head means it may grow, so nothing frees up as early.
    free_at = build_free_at(snakes, food={(2, 1)})
    assert free_at == {(1, 1): 4, (1, 2): 3, (1, 3): 2}


# --- Space -------------------------------------------------------------------


def test_flood_stops_at_a_wall_that_will_not_clear_in_time():
    # Vertical wall down x=2 that stays put, sealing off x=0..1.
    free_at = {(2, y): 99 for y in range(5)}
    reachable, food_distance = flood(
        (0, 0), free_at, width=5, height=5, food=set()
    )
    assert reachable == 10  # columns x=0 and x=1, five rows each
    assert food_distance is None


def test_flood_reports_distance_to_nearest_food():
    reachable, food_distance = flood(
        (0, 0), free_at={}, width=5, height=5, food={(0, 3)}
    )
    assert reachable == 25
    # Start square counts as distance 1, so three steps up lands on turn 4.
    assert food_distance == 4


def test_prefers_open_space_over_a_dead_end_pocket():
    # Our own body walls off a three-square pocket to the left of the head.
    # Going left fits nothing; going up is open board.
    me = [
        (1, 1),  # head
        (2, 1),  # neck
        (2, 2),
        (1, 2),
        (0, 2),
        (0, 3),
        (0, 4),
        (0, 5),
        (0, 6),
        (0, 7),
    ]
    state = make_state(me)
    assert choose_move(state) != "left"


# --- Head to head ------------------------------------------------------------


def test_avoids_a_square_a_longer_snake_can_also_reach():
    me = [(5, 5), (5, 4), (5, 3)]
    longer = [(7, 5), (8, 5), (9, 5), (10, 5), (10, 6)]
    state = make_state(me, others=[longer])
    # (6, 5) is one step from both heads and we would lose that collision.
    assert choose_move(state) != "right"


def test_declines_food_contested_by_an_equal_length_snake():
    # Regression: taken from a real self-play draw on turn 13. Food at (5, 5)
    # is one step from both heads and both snakes are length 4. Eating it does
    # not make us longer than the opponent, because they eat it too -- so this
    # is a mutual kill, not a win.
    me = [(5, 4), (6, 4), (6, 3), (5, 3)]
    equal = [(4, 5), (4, 6), (3, 6), (3, 5)]
    state = make_state(me, others=[equal], food=[(5, 5)], health=89)
    assert choose_move(state) != "up"


def test_takes_a_square_only_a_shorter_snake_can_reach():
    me = [(5, 5), (5, 4), (5, 3), (5, 2), (5, 1)]
    shorter = [(7, 5), (8, 5), (9, 5)]
    state = make_state(me, others=[shorter])
    # (6, 5) is contested, but we are longer so we win it.
    assert choose_move(state) == "right"


# --- Food --------------------------------------------------------------------


def test_moves_toward_food_when_health_is_low():
    me = [(5, 5), (5, 4), (5, 3)]
    state = make_state(me, food=[(5, 9)], health=15)
    assert choose_move(state) == "up"


def test_ignores_distant_food_in_favour_of_safety_when_healthy():
    # Food sits past a square a longer snake could take. Staying alive wins.
    me = [(5, 5), (5, 4), (5, 3)]
    longer = [(7, 5), (8, 5), (9, 5), (10, 5), (10, 6)]
    state = make_state(me, others=[longer], food=[(7, 6)], health=100)
    assert choose_move(state) != "right"


# --- Contract ----------------------------------------------------------------


def test_info_declares_api_version_and_author():
    payload = main.info()
    assert payload["apiversion"] == "1"
    assert "Daugherty" in payload["author"]


def test_move_returns_a_move_payload():
    state = make_state([(5, 5), (5, 4), (5, 3)])
    assert main.move(state)["move"] in DIRECTIONS
