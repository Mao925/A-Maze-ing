"""Tests for the public :mod:`mazegen` generation and path-finding API."""

from __future__ import annotations

from collections import deque

import pytest

from mazegen import MazeGenerationError, MazeGenerator, Point

STEP = {
    "N": (0, -1),
    "E": (1, 0),
    "S": (0, 1),
    "W": (-1, 0),
}
MOVE_BIT = {"N": 1, "E": 2, "S": 4, "W": 8}
OPPOSITE_MOVE = {"N": "S", "E": "W", "S": "N", "W": "E"}


def snapshot(maze: MazeGenerator) -> tuple[tuple[int, ...], ...]:
    """Return an immutable public-API snapshot of all wall masks."""
    return tuple(
        tuple(maze.wall_mask((x, y)) for x in range(maze.width))
        for y in range(maze.height)
    )


def distance(maze: MazeGenerator, start: Point, goal: Point) -> int:
    """Independently compute a BFS distance using wall masks."""
    queue: deque[tuple[Point, int]] = deque([(start, 0)])
    seen = {start}
    while queue:
        (x, y), length = queue.popleft()
        if (x, y) == goal:
            return length
        for name, (dx, dy) in STEP.items():
            neighbour = (x + dx, y + dy)
            nx, ny = neighbour
            if not 0 <= nx < maze.width or not 0 <= ny < maze.height:
                continue
            if maze.wall_mask((x, y)) & MOVE_BIT[name]:
                continue
            if maze.wall_mask(neighbour) & MOVE_BIT[OPPOSITE_MOVE[name]]:
                continue
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append((neighbour, length + 1))
    raise AssertionError("generated maze has no route between the test points")


@pytest.mark.parametrize("width,height", [(0, 1), (1, 0), (-1, 4)])
def test_constructor_rejects_non_positive_dimensions(
    width: int,
    height: int,
) -> None:
    """A maze must contain at least one cell in both dimensions."""
    with pytest.raises(ValueError, match="1以上"):
        MazeGenerator(width, height)


def test_wall_mask_rejects_out_of_bounds_coordinates() -> None:
    """The public cell accessor reports invalid coordinates explicitly."""
    maze = MazeGenerator(4, 3)
    with pytest.raises(ValueError, match="範囲外"):
        maze.wall_mask((4, 2))
    with pytest.raises(ValueError, match="範囲外"):
        maze.wall_mask((-1, 0))


@pytest.mark.parametrize("perfect", [True, False])
def test_seed_reproduces_the_same_maze(perfect: bool) -> None:
    """A fixed seed reproduces both perfect and playable generation."""
    first = MazeGenerator(20, 15, seed=4242)
    second = MazeGenerator(20, 15, seed=4242)
    first.generate(perfect)
    second.generate(perfect)
    assert snapshot(first) == snapshot(second)
    assert first.blocked_cells == second.blocked_cells


def test_different_seeds_change_the_generated_tree() -> None:
    """Randomness is observable when callers choose different seeds."""
    first = MazeGenerator(20, 15, seed=1)
    second = MazeGenerator(20, 15, seed=2)
    first.generate(True)
    second.generate(True)
    assert snapshot(first) != snapshot(second)


def test_shortest_path_is_valid_and_minimal() -> None:
    """The returned direction sequence follows passages and has BFS length."""
    start = (0, 0)
    goal = (19, 14)
    maze = MazeGenerator(20, 15, seed=2026)
    maze.generate(False, frozenset({start, goal}))

    path = maze.shortest_path(start, goal)
    current = start
    for move in path:
        previous = current
        dx, dy = STEP[move]
        current = (current[0] + dx, current[1] + dy)
        assert current not in maze.blocked_cells
        assert not maze.wall_mask(previous) & MOVE_BIT[move]
        assert not maze.wall_mask(current) & MOVE_BIT[OPPOSITE_MOVE[move]]
    assert current == goal
    assert len(path) == distance(maze, start, goal)


def test_shortest_path_from_a_cell_to_itself_is_empty() -> None:
    """The zero-length path is represented by an empty direction list."""
    maze = MazeGenerator(5, 5, seed=7)
    with pytest.warns(RuntimeWarning, match="42"):
        maze.generate(True)
    assert maze.shortest_path((2, 2), (2, 2)) == []


def test_shortest_path_rejects_invalid_endpoints() -> None:
    """Out-of-range and mandatory-pattern endpoints are not traversable."""
    maze = MazeGenerator(20, 15, seed=3)
    maze.generate(True)
    blocked = next(iter(maze.blocked_cells))
    with pytest.raises(ValueError, match="範囲外"):
        maze.shortest_path((-1, 0), (0, 0))
    with pytest.raises(ValueError, match="閉鎖セル"):
        maze.shortest_path(blocked, (0, 0))


def test_protected_cells_never_overlap_the_42_pattern() -> None:
    """Entry and exit candidates supplied by a caller remain traversable."""
    protected = frozenset({(1, 1), (3, 3), (18, 13)})
    maze = MazeGenerator(20, 15, seed=10)
    maze.generate(True, protected)
    assert maze.blocked_cells.isdisjoint(protected)


def test_generate_rejects_out_of_bounds_protected_cell() -> None:
    """Invalid protected coordinates fail before generation begins."""
    maze = MazeGenerator(5, 5, seed=1)
    with pytest.raises(ValueError, match="保護対象.*範囲外"):
        maze.generate(True, frozenset({(5, 0)}))


def test_small_maze_warns_when_42_cannot_be_placed() -> None:
    """Small valid mazes are generated, with the required visible warning."""
    maze = MazeGenerator(3, 3, seed=4)
    with pytest.warns(RuntimeWarning, match="42 パターン"):
        maze.generate(True)
    assert not maze.blocked_cells


def test_impossible_playable_maze_raises_generation_error() -> None:
    """A one-cell board cannot provide the two required independent loops."""
    maze = MazeGenerator(1, 1, seed=0)
    with pytest.raises(MazeGenerationError, match="独立ループ"):
        maze.generate(False)
