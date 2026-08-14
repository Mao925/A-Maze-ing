"""Structural requirement tests for generated perfect and playable mazes."""

from __future__ import annotations

from collections import deque

import pytest

from mazegen import Direction, MazeGenerator, Point

OPPOSITE = {
    Direction.N: Direction.S,
    Direction.E: Direction.W,
    Direction.S: Direction.N,
    Direction.W: Direction.E,
}
STEP = {
    Direction.N: (0, -1),
    Direction.E: (1, 0),
    Direction.S: (0, 1),
    Direction.W: (-1, 0),
}


def normal_cells(maze: MazeGenerator) -> set[Point]:
    """Return every cell not reserved for the closed ``42`` drawing."""
    return {
        (x, y)
        for y in range(maze.height)
        for x in range(maze.width)
        if (x, y) not in maze.blocked_cells
    }


def passages(maze: MazeGenerator, point: Point) -> set[Point]:
    """Read coherent open neighbours using only the public wall API."""
    x, y = point
    result: set[Point] = set()
    for direction, (dx, dy) in STEP.items():
        neighbour = (x + dx, y + dy)
        nx, ny = neighbour
        if not 0 <= nx < maze.width or not 0 <= ny < maze.height:
            continue
        if maze.wall_mask(point) & int(direction):
            continue
        if maze.wall_mask(neighbour) & int(OPPOSITE[direction]):
            continue
        result.add(neighbour)
    return result


def reachable(maze: MazeGenerator, start: Point) -> set[Point]:
    """Return the connected component containing ``start``."""
    seen = {start}
    queue: deque[Point] = deque([start])
    while queue:
        for neighbour in passages(maze, queue.popleft()):
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    return seen


def graph_counts(maze: MazeGenerator) -> tuple[int, int, int]:
    """Return normal vertices, open edges, and independent cycle count."""
    cells = normal_cells(maze)
    edges = sum(len(passages(maze, point)) for point in cells) // 2
    return len(cells), edges, edges - len(cells) + 1


def actionable_dead_ends(maze: MazeGenerator) -> int:
    """Count degree-one cells whose closed wall could still be opened."""
    cells = normal_cells(maze)
    count = 0
    for point in cells:
        if len(passages(maze, point)) != 1:
            continue
        x, y = point
        if any(
            (x + dx, y + dy) in cells
            and maze.wall_mask(point) & int(direction)
            for direction, (dx, dy) in STEP.items()
        ):
            count += 1
    return count


def has_open_3x3(maze: MazeGenerator) -> bool:
    """Return whether any 3x3 window has all twelve internal walls open."""
    for top in range(maze.height - 2):
        for left in range(maze.width - 2):
            horizontal = all(
                not maze.wall_mask((left + dx, top + dy))
                & int(Direction.E)
                for dy in range(3)
                for dx in range(2)
            )
            vertical = all(
                not maze.wall_mask((left + dx, top + dy))
                & int(Direction.S)
                for dy in range(2)
                for dx in range(3)
            )
            if horizontal and vertical:
                return True
    return False


@pytest.fixture(params=[0, 7, 42])
def perfect_maze(request: pytest.FixtureRequest) -> MazeGenerator:
    """Generate representative seeded perfect mazes."""
    maze = MazeGenerator(20, 15, seed=int(request.param))
    maze.generate(True, frozenset({(0, 0), (19, 14)}))
    return maze


@pytest.fixture(params=[0, 7, 42])
def playable_maze(request: pytest.FixtureRequest) -> MazeGenerator:
    """Generate representative seeded Pac-Man-style mazes."""
    maze = MazeGenerator(20, 15, seed=int(request.param))
    maze.generate(False, frozenset({(0, 0), (19, 14)}))
    return maze


@pytest.fixture(
    params=[
        (True, 0),
        (True, 7),
        (True, 42),
        (False, 0),
        (False, 7),
        (False, 42),
    ],
)
def generated_maze(request: pytest.FixtureRequest) -> MazeGenerator:
    """Generate both modes for tests of their shared invariants."""
    perfect, seed = request.param
    maze = MazeGenerator(20, 15, seed=int(seed))
    maze.generate(bool(perfect), frozenset({(0, 0), (19, 14)}))
    return maze


def test_wall_values_outer_border_and_shared_walls_are_valid(
    generated_maze: MazeGenerator,
) -> None:
    """Masks stay hexadecimal-sized and every physical wall agrees."""
    maze = generated_maze
    for y in range(maze.height):
        for x in range(maze.width):
            point = (x, y)
            mask = maze.wall_mask(point)
            assert 0 <= mask <= 0xF
            if y == 0:
                assert mask & int(Direction.N)
            if x == maze.width - 1:
                assert mask & int(Direction.E)
            if y == maze.height - 1:
                assert mask & int(Direction.S)
            if x == 0:
                assert mask & int(Direction.W)
            for direction, (dx, dy) in STEP.items():
                neighbour = (x + dx, y + dy)
                nx, ny = neighbour
                if 0 <= nx < maze.width and 0 <= ny < maze.height:
                    assert bool(mask & int(direction)) == bool(
                        maze.wall_mask(neighbour)
                        & int(OPPOSITE[direction])
                    )


def test_all_non_pattern_cells_are_connected(
    generated_maze: MazeGenerator,
) -> None:
    """Only fully closed cells drawing ``42`` may be unreachable."""
    maze = generated_maze
    cells = normal_cells(maze)
    assert reachable(maze, min(cells)) == cells
    assert maze.blocked_cells
    assert all(maze.wall_mask(point) == 0xF for point in maze.blocked_cells)


def test_blocked_cells_visibly_form_42(
    perfect_maze: MazeGenerator,
) -> None:
    """The fully closed cells preserve the required glyph, not just a count."""
    expected_pattern = (
        "#.#.###",
        "#.#...#",
        "###.###",
        "..#.#..",
        "..#.###",
    )
    left = min(x for x, _y in perfect_maze.blocked_cells)
    top = min(y for _x, y in perfect_maze.blocked_cells)
    normalized = {
        (x - left, y - top) for x, y in perfect_maze.blocked_cells
    }
    expected = {
        (x, y)
        for y, row in enumerate(expected_pattern)
        for x, marker in enumerate(row)
        if marker == "#"
    }
    assert normalized == expected


def test_perfect_maze_is_a_spanning_tree(
    perfect_maze: MazeGenerator,
) -> None:
    """Connected perfect output has V-1 edges and therefore no cycles."""
    vertices, edges, loops = graph_counts(perfect_maze)
    assert edges == vertices - 1
    assert loops == 0


def test_playable_maze_has_multiple_routes_and_few_dead_ends(
    playable_maze: MazeGenerator,
) -> None:
    """Playable output has at least two cycles and at most two real ends."""
    _vertices, _edges, loops = graph_counts(playable_maze)
    assert loops >= 2
    assert actionable_dead_ends(playable_maze) <= 2


def test_playable_corners_and_centre_are_corridors(
    playable_maze: MazeGenerator,
) -> None:
    """Pac-Man key positions belong to the reachable corridor graph."""
    cells = normal_cells(playable_maze)
    key_cells = {
        (0, 0),
        (playable_maze.width - 1, 0),
        (0, playable_maze.height - 1),
        (playable_maze.width - 1, playable_maze.height - 1),
        (playable_maze.width // 2, playable_maze.height // 2),
    }
    assert key_cells <= cells
    assert all(passages(playable_maze, point) for point in key_cells)


def test_no_fully_open_3x3_area(
    generated_maze: MazeGenerator,
) -> None:
    """Generated corridors never form a forbidden broad open room."""
    maze = generated_maze
    assert not has_open_3x3(maze)
