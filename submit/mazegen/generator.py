"""A-Maze-ing の迷路生成・解法・検証を担当するモジュール。

担当者Aは、このモジュールに迷路生成ロジックを実装します。
担当者Bは ``MazeGenerator`` の公開APIだけを使い、``_grid`` などの
内部状態へ直接アクセスしません。
"""

from __future__ import annotations

import random
import warnings
from collections import deque
from enum import IntEnum

Point = tuple[int, int]  # (x, y)。左上が (0, 0)


class Direction(IntEnum):
    """壁の方向。整数値はその壁ビットを表す。"""

    N = 1
    E = 2
    S = 4
    W = 8


STEPS: dict[Direction, Point] = {
    Direction.N: (0, -1),
    Direction.E: (1, 0),
    Direction.S: (0, 1),
    Direction.W: (-1, 0),
}

OPPOSITE: dict[Direction, Direction] = {
    Direction.N: Direction.S,
    Direction.E: Direction.W,
    Direction.S: Direction.N,
    Direction.W: Direction.E,
}

ALL_WALLS: int = Direction.N | Direction.E | Direction.S | Direction.W

FORTY_TWO_PATTERN: tuple[str, ...] = (
    "#.#.###",
    "#.#...#",
    "###.###",
    "..#.#..",
    "..#.###",
)

MAX_GENERATION_ATTEMPTS = 20


class MazeGenerationError(RuntimeError):
    """迷路生成が再試行上限まで失敗したことを示す例外。"""


class MazeGenerator:
    """幅・高さ・シードを指定して迷路を生成するクラス。"""

    def __init__(
        self,
        width: int,
        height: int,
        seed: int | None = None,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("width と height は1以上でなければなりません")

        self.width = width
        self.height = height
        self._seed = seed
        self._grid: list[list[int]] = []
        self._blocked_cells: frozenset[Point] = frozenset()
        self._reset()

    def generate(
        self,
        perfect: bool,
        protected_cells: frozenset[Point] = frozenset(),
    ) -> None:
        """指定モードの迷路を生成し、検証を通過した結果を採用する。

        ``perfect=True`` なら完全迷路、``False`` ならループ付き迷路を作ります。
        ``protected_cells`` は入口・出口など、``42`` と重ねてはいけない座標です。
        """
        invalid = sorted(
            point for point in protected_cells if not self._in_bounds(point)
        )
        if invalid:
            raise ValueError(f"保護対象の座標が迷路の範囲外です: {invalid}")

        random_seed = self._seed
        if random_seed is None:
            random_seed = random.SystemRandom().randrange(2**63)

        last_errors: list[str] = []
        for attempt in range(MAX_GENERATION_ATTEMPTS):
            self._reset()
            self._blocked_cells = self._choose_42_cells(protected_cells)
            rng = random.Random(random_seed + attempt)
            self._generate_spanning_tree(rng)
            if not perfect:
                self._add_loops(rng)
                self._reduce_dead_ends(rng)

            last_errors = self._validation_errors(perfect, protected_cells)
            if not last_errors:
                if not self._blocked_cells:
                    warnings.warn(
                        "迷路が小さい、または保護座標と重なるため "
                        "42 パターンを配置できませんでした",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                return

        details = "; ".join(last_errors) or "原因を特定できませんでした"
        raise MazeGenerationError(
            f"{MAX_GENERATION_ATTEMPTS} 回試行しても有効な迷路を"
            f"生成できませんでした: {details}"
        )

    def shortest_path(self, start: Point, goal: Point) -> list[str]:
        """BFSで最短経路を求め、移動方向の列（例: ``['E', 'E', 'S']``）を返す。

        開始セルは返り値に含めません。範囲外・閉鎖セル・経路なしは
        ``ValueError`` にします。
        """
        for name, point in (("start", start), ("goal", goal)):
            if not self._in_bounds(point):
                raise ValueError(f"{name} が迷路の範囲外です: {point}")
            if point in self._blocked_cells:
                raise ValueError(f"{name} は 42 の閉鎖セルです: {point}")

        parents: dict[Point, tuple[Point, str]] = {}
        seen = {start}
        queue: deque[Point] = deque([start])
        while queue and goal not in seen:
            current = queue.popleft()
            for neighbour, direction in self._passages(current):
                if neighbour in seen:
                    continue
                seen.add(neighbour)
                parents[neighbour] = (current, direction.name)
                queue.append(neighbour)

        if goal not in seen:
            raise ValueError(f"{start} から {goal} への経路がありません")

        path: list[str] = []
        current = goal
        while current != start:
            current, move_name = parents[current]
            path.append(move_name)
        path.reverse()
        return path

    def wall_mask(self, point: Point) -> int:
        """指定セルの壁ビット（0〜15）を返す。"""
        if not self._in_bounds(point):
            raise ValueError(f"座標が迷路の範囲外です: {point}")

        x, y = point
        return self._grid[y][x]

    @property
    def blocked_cells(self) -> frozenset[Point]:
        """``42`` を構成する完全閉鎖セルを返す。"""
        return self._blocked_cells

    def _reset(self) -> None:
        """全セルを4壁閉鎖の状態に戻す。"""
        self._grid = [
            [ALL_WALLS for _ in range(self.width)]
            for _ in range(self.height)
        ]
        self._blocked_cells = frozenset()

    def _in_bounds(self, point: Point) -> bool:
        """座標が迷路の範囲内なら True を返す。"""
        x, y = point
        return 0 <= x < self.width and 0 <= y < self.height

    def _neighbour(self, point: Point, direction: Direction) -> Point:
        """指定方向の隣接座標を返す。範囲チェックは行わない。"""
        x, y = point
        dx, dy = STEPS[direction]
        return (x + dx, y + dy)

    def _remove_wall(self, point: Point, direction: Direction) -> None:
        """point側の壁と、隣接セル側の反対壁を同時に開ける。"""
        x, y = point
        neighbour = self._neighbour(point, direction)
        if not self._in_bounds(neighbour):
            raise ValueError("隣接セルが迷路の範囲外です")

        nx, ny = neighbour
        self._grid[y][x] &= ALL_WALLS ^ int(direction)
        self._grid[ny][nx] &= ALL_WALLS ^ int(OPPOSITE[direction])

    def _add_wall(self, point: Point, direction: Direction) -> None:
        """試行を戻すため、point側の壁と反対側の共有壁を同時に閉じる。"""
        x, y = point
        neighbour = self._neighbour(point, direction)
        if not self._in_bounds(neighbour):
            raise ValueError("隣接セルが迷路の範囲外です")

        nx, ny = neighbour
        self._grid[y][x] |= int(direction)
        self._grid[ny][nx] |= int(OPPOSITE[direction])

    def _choose_42_cells(
        self,
        protected_cells: frozenset[Point],
    ) -> frozenset[Point]:
        """配置可能な ``42`` の閉鎖セル集合を決めて返す。

        配置できない場合は空集合を返します。
        """
        pattern_height = len(FORTY_TWO_PATTERN)
        pattern_width = len(FORTY_TWO_PATTERN[0])
        if self.width < pattern_width + 2 or self.height < pattern_height + 2:
            return frozenset()

        reserved = set(protected_cells) | self._key_cells()
        all_cells = {
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
        }
        for top in range(1, self.height - pattern_height):
            for left in range(1, self.width - pattern_width):
                pattern_cells = frozenset(
                    (left + x, top + y)
                    for y, row in enumerate(FORTY_TWO_PATTERN)
                    for x, marker in enumerate(row)
                    if marker == "#"
                )
                if pattern_cells & reserved:
                    continue

                normal_cells = all_cells - pattern_cells
                start = min(normal_cells)
                seen = {start}
                stack = [start]
                while stack:
                    point = stack.pop()
                    for direction in Direction:
                        neighbour = self._neighbour(point, direction)
                        if neighbour in normal_cells and neighbour not in seen:
                            seen.add(neighbour)
                            stack.append(neighbour)
                if seen == normal_cells:
                    return pattern_cells
        return frozenset()

    def _generate_spanning_tree(self, rng: random.Random) -> None:
        """反復版DFSで、閉鎖セル以外の通常セルを連結する完全迷路を作る。"""
        normal_cells = self._normal_cells()
        if not normal_cells:
            return

        start = rng.choice(sorted(normal_cells))
        visited = {start}
        stack = [start]
        while stack:
            current = stack[-1]
            candidates = [
                (neighbour, direction)
                for direction in Direction
                if (
                    (neighbour := self._neighbour(current, direction))
                    in normal_cells
                    and neighbour not in visited
                )
            ]
            if not candidates:
                stack.pop()
                continue
            neighbour, direction = rng.choice(candidates)
            self._remove_wall(current, direction)
            visited.add(neighbour)
            stack.append(neighbour)

        if visited != normal_cells:
            raise MazeGenerationError(
                "42 パターン以外のセルを一つの迷路として連結できません"
            )

    def _add_loops(self, rng: random.Random) -> None:
        """3×3制約を守りながら、独立ループが2以上になるまで壁を開ける。"""
        candidates = self._closed_wall_candidates()
        rng.shuffle(candidates)
        for point, direction in candidates:
            if self._loop_count() >= 2:
                return
            self._remove_wall(point, direction)
            if self._has_open_3x3():
                self._add_wall(point, direction)

    def _reduce_dead_ends(self, rng: random.Random) -> None:
        """行き止まりが2以下になるまで、安全に壁を開ける。"""
        while self._dead_end_count() > 2:
            dead_ends = [
                point
                for point in self._normal_cells()
                if len(self._passages(point)) == 1
            ]
            rng.shuffle(dead_ends)
            changed = False
            for point in dead_ends:
                candidates = [
                    (candidate, direction)
                    for candidate, direction
                    in self._closed_wall_candidates(point)
                ]
                rng.shuffle(candidates)
                for candidate, direction in candidates:
                    self._remove_wall(candidate, direction)
                    if self._has_open_3x3():
                        self._add_wall(candidate, direction)
                        continue
                    changed = True
                    break
                if changed:
                    break
            if not changed:
                return

    def _passages(self, point: Point) -> list[tuple[Point, Direction]]:
        """pointから壁が開いていて実際に移動できる隣接セルと方向を返す。"""
        if not self._in_bounds(point) or point in self._blocked_cells:
            return []

        x, y = point
        passages: list[tuple[Point, Direction]] = []
        for direction in Direction:
            neighbour = self._neighbour(point, direction)
            if not self._in_bounds(neighbour):
                continue
            if neighbour in self._blocked_cells:
                continue
            nx, ny = neighbour
            if self._grid[y][x] & int(direction):
                continue
            if self._grid[ny][nx] & int(OPPOSITE[direction]):
                continue
            passages.append((neighbour, direction))
        return passages

    def _reachable_cells(self, start: Point) -> set[Point]:
        """BFSで start から到達可能な通常セルの集合を返す。"""
        if not self._in_bounds(start) or start in self._blocked_cells:
            return set()
        seen = {start}
        queue: deque[Point] = deque([start])
        while queue:
            current = queue.popleft()
            for neighbour, _direction in self._passages(current):
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        return seen

    def _loop_count(self) -> int:
        """通常セルのグラフについて ``E - V + 1`` で独立ループ数を返す。"""
        normal_cells = self._normal_cells()
        if not normal_cells:
            return 0
        edges = sum(len(self._passages(point)) for point in normal_cells) // 2
        return max(edges - len(normal_cells) + 1, 0)

    def _dead_end_count(self) -> int:
        """追加の壁開放で解消できる次数1の通常セル数を返す。

        外周と ``42`` の閉鎖セルだけに囲まれた行き止まりは、配布済み
        analyzer と同様にパターン配置に伴う不可避なものとして除外します。
        """
        return sum(
            len(self._passages(point)) == 1
            and bool(self._closed_wall_candidates(point))
            for point in self._normal_cells()
        )

    def _has_open_3x3(self) -> bool:
        """完全開放された3×3領域が1つでもあれば True を返す。"""
        for top in range(self.height - 2):
            for left in range(self.width - 2):
                cells = {
                    (left + dx, top + dy)
                    for dy in range(3)
                    for dx in range(3)
                }
                if cells & self._blocked_cells:
                    continue
                horizontal = all(
                    not self.wall_mask((left + dx, top + dy))
                    & int(Direction.E)
                    for dy in range(3)
                    for dx in range(2)
                )
                vertical = all(
                    not self.wall_mask((left + dx, top + dy))
                    & int(Direction.S)
                    for dy in range(2)
                    for dx in range(3)
                )
                if horizontal and vertical:
                    return True
        return False

    def _validation_errors(
        self,
        perfect: bool,
        protected_cells: frozenset[Point],
    ) -> list[str]:
        """不変条件とモード要件をまとめて検証し、エラー文言のリストを返す。"""
        errors: list[str] = []
        if len(self._grid) != self.height or any(
            len(row) != self.width for row in self._grid
        ):
            return ["壁グリッドの寸法が width/height と一致しません"]

        for y, row in enumerate(self._grid):
            for x, mask in enumerate(row):
                if not isinstance(mask, int) or not 0 <= mask <= ALL_WALLS:
                    errors.append(f"セル {(x, y)} の壁値が不正です: {mask}")

        for point in protected_cells:
            if not self._in_bounds(point):
                errors.append(f"保護対象の座標が範囲外です: {point}")
            elif point in self._blocked_cells:
                errors.append(f"保護対象の座標が 42 と重なっています: {point}")

        for point in self._blocked_cells:
            if not self._in_bounds(point):
                errors.append(f"42 の座標が範囲外です: {point}")
            elif self.wall_mask(point) != ALL_WALLS:
                errors.append(f"42 のセルが完全閉鎖されていません: {point}")

        for y in range(self.height):
            for x in range(self.width):
                point = (x, y)
                mask = self.wall_mask(point)
                if y == 0 and not mask & int(Direction.N):
                    errors.append(f"北外周が開いています: {point}")
                if x == self.width - 1 and not mask & int(Direction.E):
                    errors.append(f"東外周が開いています: {point}")
                if y == self.height - 1 and not mask & int(Direction.S):
                    errors.append(f"南外周が開いています: {point}")
                if x == 0 and not mask & int(Direction.W):
                    errors.append(f"西外周が開いています: {point}")

                for direction in (Direction.E, Direction.S):
                    neighbour = self._neighbour(point, direction)
                    if not self._in_bounds(neighbour):
                        continue
                    nx, ny = neighbour
                    closed_here = bool(mask & int(direction))
                    closed_there = bool(
                        self._grid[ny][nx] & int(OPPOSITE[direction])
                    )
                    if closed_here != closed_there:
                        errors.append(
                            f"共有壁が一致しません: {point} {direction.name}"
                        )

        normal_cells = self._normal_cells()
        if not normal_cells:
            errors.append("通路として使える通常セルがありません")
        else:
            start = min(normal_cells)
            if self._reachable_cells(start) != normal_cells:
                errors.append("42 以外のセルがすべて連結されていません")

        if self._has_open_3x3():
            errors.append("完全開放された 3x3 領域があります")

        loops = self._loop_count()
        if perfect and loops != 0:
            errors.append(f"完全迷路に {loops} 個の独立ループがあります")
        if not perfect:
            if loops < 2:
                errors.append(f"独立ループが不足しています: {loops} < 2")
            dead_ends = self._dead_end_count()
            if dead_ends > 2:
                errors.append(f"行き止まりが多すぎます: {dead_ends} > 2")
            unavailable = self._key_cells() - normal_cells
            if unavailable:
                errors.append(
                    "四隅または中央が通路ではありません: "
                    f"{sorted(unavailable)}"
                )
        return errors

    def _normal_cells(self) -> set[Point]:
        """``42`` を除く全座標を返す。"""
        return {
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
            if (x, y) not in self._blocked_cells
        }

    def _key_cells(self) -> set[Point]:
        """非完全迷路で保護する四隅と中央候補を返す。"""
        x_mid = {self.width // 2}
        y_mid = {self.height // 2}
        if self.width % 2 == 0:
            x_mid.add(self.width // 2 - 1)
        if self.height % 2 == 0:
            y_mid.add(self.height // 2 - 1)
        corners = {
            (0, 0),
            (self.width - 1, 0),
            (0, self.height - 1),
            (self.width - 1, self.height - 1),
        }
        return corners | {(x, y) for y in y_mid for x in x_mid}

    def _closed_wall_candidates(
        self,
        only_from: Point | None = None,
    ) -> list[tuple[Point, Direction]]:
        """通常セル間に残る閉じた共有壁を重複なく列挙する。"""
        points = {only_from} if only_from is not None else self._normal_cells()
        candidates: list[tuple[Point, Direction]] = []
        normal_cells = self._normal_cells()
        for point in sorted(points):
            if point not in normal_cells:
                continue
            x, y = point
            for direction in Direction:
                neighbour = self._neighbour(point, direction)
                if neighbour not in normal_cells:
                    continue
                if only_from is None and neighbour < point:
                    continue
                if self._grid[y][x] & int(direction):
                    candidates.append((point, direction))
        return candidates
