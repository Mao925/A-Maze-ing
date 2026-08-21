#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from collections import deque
from dataclasses import dataclass
from enum import IntFlag
from functools import cached_property
from typing import Dict, FrozenSet, Iterator, List, Optional, Set, Tuple

Cell = Tuple[int, int]                 # 変更できない (行, 列) 座標


class Direction(IntFlag):
    """壁の方向。整数値はファイル内で使う壁ビットを表す。"""

    NORTH = 1
    EAST = 2
    SOUTH = 4
    WEST = 8

    @property
    def opposite(self) -> "Direction":
        """隣接セル側から見た、同じ共有壁の反対方向を返す。"""
        return _OPPOSITE[self]

    @property
    def step(self) -> Cell:
        """この方向にある隣接セルへの (行, 列) の移動量を返す。"""
        return _STEP[self]


_OPPOSITE: Dict[Direction, Direction] = {
    Direction.NORTH: Direction.SOUTH,
    Direction.SOUTH: Direction.NORTH,
    Direction.EAST: Direction.WEST,
    Direction.WEST: Direction.EAST,
}
_STEP: Dict[Direction, Cell] = {
    Direction.NORTH: (-1, 0),
    Direction.EAST: (0, 1),
    Direction.SOUTH: (1, 0),
    Direction.WEST: (0, -1),
}
ALL_WALLS = Direction.NORTH | Direction.EAST | Direction.SOUTH | Direction.WEST

DEFAULT_MIN_LOOPS = 2
DEFAULT_MAX_DEAD_ENDS = 2
EXIT_OK = 0
EXIT_MALFORMED = 2

HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


class MazeError(Exception):
    """入力ファイルを迷路グリッドとして解析できない場合の例外。"""


class Maze:
    """解析済みの迷路。壁グリッドと入口・出口のセルを保持する。

    グリッドはセルごとに1つの整数を持ち、ビットが1の方向を
    *閉じた壁*として表す。接続性の分析は、隣接セル間の開いた通路を
    辺とするグラフに対するビット演算だけで行える。
    """

    def __init__(self, grid: List[List[int]], entry: Optional[Cell],
                 exit: Optional[Cell]) -> None:
        self.grid = grid
        self.entry = entry
        self.exit = exit
        self.rows = len(grid)
        self.cols = len(grid[0]) if grid else 0

    # -- 構築 --------------------------------------------------------------- #
    @classmethod
    def from_file(cls, path: str) -> "Maze":
        """*path*を解析する。不正なグリッドの場合は :class:`MazeError` を送出する。"""
        grid: List[List[int]] = []
        footer: List[str] = []
        reading_grid = True
        with open(path, encoding="utf-8", errors="replace") as stream:
            for number, raw in enumerate(stream, start=1):
                line = raw.rstrip("\n\r")
                if reading_grid:
                    if not line.strip():
                        reading_grid = False
                        continue
                    cells = line.strip(" \t")
                    grid.append(cls._parse_row(cells, number, grid))
                elif line.strip():
                    footer.append(line.strip())
        if not grid:
            raise MazeError("no grid rows were found before the footer.")
        entry = cls._parse_coordinate(footer[0]) if footer else None
        exit_ = cls._parse_coordinate(footer[1]) if len(footer) > 1 else None
        return cls(grid, entry, exit_)

    @staticmethod
    def _parse_row(text: str, number: int, grid: List[List[int]]) -> List[int]:
        row = []
        for column, char in enumerate(text, start=1):
            if char not in HEX_DIGITS:
                raise MazeError(
                    f"line {number}, column {column}: {char!r} is not a "
                    f"hexadecimal digit (the grid must use digits 0-F)."
                )
            row.append(int(char, 16))
        if grid and len(row) != len(grid[0]):
            raise MazeError(
                f"line {number}: row has {len(row)} cells but the first row "
                f"has {len(grid[0])} (the grid must be rectangular)."
            )
        return row

    @staticmethod
    def _parse_coordinate(text: str) -> Optional[Cell]:
        try:
            x_text, y_text = text.split(",")
            return int(y_text), int(x_text)
        except ValueError:
            return None

    def __contains__(self, cell: Cell) -> bool:
        row, col = cell
        return 0 <= row < self.rows and 0 <= col < self.cols

    def __iter__(self) -> Iterator[Cell]:
        for row in range(self.rows):
            for col in range(self.cols):
                yield row, col

    def walls(self, cell: Cell) -> int:
        return self.grid[cell[0]][cell[1]]

    def is_fully_closed(self, cell: Cell) -> bool:
        """必須の「42」パターンを描く、完全に閉じたセルならTrueを返す。"""
        return self.walls(cell) == ALL_WALLS

    def neighbour(self, cell: Cell, side: Direction) -> Cell:
        return cell[0] + side.step[0], cell[1] + side.step[1]

    def is_open(self, cell: Cell, side: Direction) -> bool:
        """*side*方向の共有壁が、両方の隣接セルで開いていればTrueを返す。"""
        other = self.neighbour(cell, side)
        if other not in self:
            return False
        return not (self.walls(cell) & side) \
            and not (self.walls(other) & side.opposite)

    def passages(self, cell: Cell) -> Iterator[Cell]:
        """*cell*と開いた通路を共有する隣接セルを順に返す。"""
        for side in Direction:
            if self.is_open(cell, side):
                yield self.neighbour(cell, side)

    def region_of(self, start: Cell) -> FrozenSet[Cell]:
        """*start*から到達できるセルを幅優先探索で求めて返す。"""
        seen = {start}
        queue = deque([start])
        while queue:
            for nxt in self.passages(queue.popleft()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return frozenset(seen)

    def largest_region(self) -> FrozenSet[Cell]:
        """一度の走査で求めた、最大の連結成分を返す。"""
        seen: Set[Cell] = set()
        best: FrozenSet[Cell] = frozenset()
        for cell in self:
            if cell in seen:
                continue
            component = self.region_of(cell)
            seen |= component
            if len(component) > len(best):
                best = component
        return best

    def incoherent_cells(self) -> Tuple[Cell, ...]:
        """隣接セルと壁の表現が一致していないセルを返す。"""
        return tuple(
            cell
            for cell in self
            if any(
                self.neighbour(cell, side) in self
                and bool(self.walls(cell) & side)
                != bool(self.walls(self.neighbour(cell, side)) & side.opposite)
                for side in Direction
            )
        )


@dataclass(frozen=True)
class MazeReport:
    """迷路のプレイ可能領域についての接続性の測定結果。

    基本となる数値だけを保存し、比率や判定は必要になった時点で計算する。
    そのため、レポートは迷路の状態を軽量に表す自己完結したスナップショットになる。
    """

    maze: Maze
    region: FrozenSet[Cell]
    entry: Cell
    entry_from_footer: bool
    incoherent: Tuple[Cell, ...]

    @cached_property
    def open_passages(self) -> int:
        """領域グラフの辺の数（各通路を1回だけ数える）。"""
        return sum(
            1
            for cell in self.region
            for nxt in self.maze.passages(cell)
            if nxt in self.region and nxt > cell
        )

    @cached_property
    def potential_passages(self) -> int:
        """内部の壁をすべて開けた場合に領域が持つ辺の数。"""
        return sum(
            ((r, c + 1) in self.region) + ((r + 1, c) in self.region)
            for r, c in self.region
        )

    @property
    def loops(self) -> int:
        """独立したループ数。1つの連結成分では ``辺 - 頂点 + 1`` で求める。"""
        return self.open_passages - len(self.region) + 1

    @property
    def max_loops(self) -> int:
        return max(self.potential_passages - max(len(self.region) - 1, 0), 0)

    @property
    def path_ratio(self) -> float:
        return self.loops / self.max_loops if self.max_loops else 0.0

    @property
    def isolated(self) -> int:
        return self.maze.rows * self.maze.cols - len(self.region)

    @cached_property
    def disconnected_corridors(self) -> int:
        """プレイ可能領域の外にある、"42"の壁ではないセルの数。

        プレイヤーが決して到達できない通路にあたる。Pac-Man風のステージでは
        アイテムを回収できず、クリアできないステージになってしまう。
        """
        return sum(
            1
            for cell in self.maze
            if cell not in self.region and not self.maze.is_fully_closed(cell)
        )

    @property
    def exit_reachable(self) -> Optional[bool]:
        if self.maze.exit is None:
            return None
        return self.maze.exit in self.region

    @cached_property
    def dead_ends(self) -> Tuple[int, int]:
        """通路が1つだけのセルの数を ``(通常, "42"に囲まれたもの)`` で返す。

        閉じた壁のうち通常セル側を1つ開けられるものを*通常の行き止まり*とする。
        すべての閉じた壁が完全閉鎖された"42"セルまたは外周に面している場合は、
        *囲まれた行き止まり*として許容する。
        """
        real = enclosed = 0
        for cell in self.region:
            if sum(1 for _ in self.maze.passages(cell)) != 1:
                continue
            if self._has_openable_wall(cell):
                real += 1
            else:
                enclosed += 1
        return real, enclosed

    def _has_openable_wall(self, cell: Cell) -> bool:
        return any(
            (self.maze.walls(cell) & side)
            and self.maze.neighbour(cell, side) in self.maze
            and not self.maze.is_fully_closed(self.maze.neighbour(cell, side))
            for side in Direction
        )

    @cached_property
    def unreachable_key_cells(self) -> Tuple[Cell, ...]:
        """Pac-Man用に通路である必要がある四隅と中央を確認する。

        行数・列数が奇数なら中央は1セルになる。偶数の場合は中央に
        ぴったり該当するセルがないため、中央を囲む最大4セルのいずれかを
        スタート地点として許可する。
        """
        rows, cols = self.maze.rows, self.maze.cols
        corners = {(0, 0), (0, cols - 1), (rows - 1, 0), (rows - 1, cols - 1)}
        missing = {cell for cell in corners if cell not in self.region}
        centre_candidates = self._centre_candidates()
        if not any(cell in self.region for cell in centre_candidates):
            missing |= centre_candidates
        return tuple(sorted(missing))

    def _centre_candidates(self) -> FrozenSet[Cell]:
        """幅・高さが偶数の場合も考慮して、中央付近のセルを返す。"""
        rows, cols = self.maze.rows, self.maze.cols
        row_mid = {rows // 2} if rows % 2 else {rows // 2 - 1, rows // 2}
        col_mid = {cols // 2} if cols % 2 else {cols // 2 - 1, cols // 2}
        return frozenset((r, c) for r in row_mid for c in col_mid)


def analyze(maze: Maze) -> MazeReport:
    """プレイ可能領域（入口からの領域、または最大領域）を選び、測定する。"""
    if maze.entry is not None and maze.entry in maze:
        region, from_footer = maze.region_of(maze.entry), True
        entry = maze.entry
    else:
        region = maze.largest_region()
        entry = min(region) if region else (0, 0)
        from_footer = False
    return MazeReport(
        maze, region, entry, from_footer, maze.incoherent_cells()
    )


def verdict(report: MazeReport, min_loops: int, max_dead_ends: int) -> str:
    """*report*に対する結論を1行で返す。

        プレイ可能（非完全）判定は、調整可能で数値化された2つの基準で決まる。

        * *min_loops* - Pac-Man用の盤面に必要な独立経路数（デフォルトは2。
            完全迷路から壁を1つ開けただけのループ1つでは不十分）。
        * *max_dead_ends* - 許容する通常の行き止まり数（デフォルトは2。0にすると
            行き止まりのない、完全に編み込まれた盤面を要求する）。
    """
    real_dead_ends = report.dead_ends[0]
    if report.incoherent:
        return (
            f"INCOHERENT walls: {len(report.incoherent)} cell(s) encode a "
            f"shared wall differently from their neighbour - the maze is "
            f"invalid (fix the encoding first)."
        )
    if len(report.region) <= 1:
        return (
            "DEGENERATE: the entry has no open passage (no navigable "
            "corridors) - check the wall encoding and the entry cell."
        )
    if report.disconnected_corridors:
        return (
            f"NOT fully connected: {report.disconnected_corridors} corridor "
            f"cell(s) cannot be reached from the entry - a Pac-Man level here "
            f"would be unwinnable (only the '42' cells may be isolated)."
        )
    if report.loops == 0:
        return (
            "PERFECT maze: a single path, no loop -> matches PERFECT=True "
            "(this is not a multi-route board for Pac-Man)."
        )
    if report.unreachable_key_cells:
        return (
            "Not Pac-Man-ready: the player start (centre) or a corner is not "
            "an open corridor - ghosts, super-pacgums or the player can't be "
            "placed."
        )
    if report.loops < min_loops:
        return (
            f"Not Pac-Man-ready: only {report.loops} independent route(s); a "
            f"usable board needs at least {min_loops} so a chased player "
            f"always has an alternative."
        )
    if real_dead_ends > max_dead_ends:
        return (
            f"Not Pac-Man-ready: {real_dead_ends} real dead-ends (at most "
            f"{max_dead_ends} tolerated) - too many traps for a chased player."
        )
    extra = (
        "no real dead-end -> bonus-grade (perfectly braided)"
        if real_dead_ends == 0 else
        f"{real_dead_ends} real dead-end(s) within tolerance "
        f"(0 would be bonus-grade)"
    )
    return (
        f"Pac-Man-USABLE: fully connected, corners and centre reachable, "
        f"{report.loops} independent routes; {extra}."
    )


def render(report: MazeReport, min_loops: int, max_dead_ends: int) -> str:
    """人間が読みやすい完全なレポートを作成する。"""
    maze = report.maze
    real, enclosed = report.dead_ends
    lines = [
        f"Maze size        : {maze.cols} x {maze.rows} "
        f"({maze.rows * maze.cols} cells)",
        f"Entry            : {_xy(report.entry)}   Exit: {_exit(report)}",
    ]
    if not report.entry_from_footer:
        lines.append("                   (no valid entry in footer; using the "
                     "largest reachable region)")
    lines += [
        f"Reachable region : {len(report.region)} cells "
        f"({report.disconnected_corridors} corridor(s) unreachable)",
        f"Independent loops: {report.loops} / {report.max_loops} possible "
        f"(path ratio {report.path_ratio:.0%})",
        f"Dead-ends        : {real} real + {enclosed} enclosed by the '42' "
        f"(tolerated)",
        f"Corners + centre : {_key_cells(report.unreachable_key_cells)}",
        f"Wall coherence   : {_coherence(report.incoherent)}",
        "",
        f"Verdict: {verdict(report, min_loops, max_dead_ends)}",
    ]
    return "\n".join(lines)


def _xy(cell: Cell) -> str:
    """内部の ``(行, 列)`` セルを課題の ``(x, y)`` 表記に変換する。"""
    return f"({cell[1]}, {cell[0]})"


def _exit(report: MazeReport) -> str:
    if report.maze.exit is None:
        return "?"
    states: Dict[Optional[bool], str] = {
        True: " (reachable)", False: " (UNREACHABLE)",
    }
    state = states.get(report.exit_reachable, "")
    return f"{_xy(report.maze.exit)}{state}"


def _key_cells(cells: Tuple[Cell, ...]) -> str:
    if not cells:
        return "all reachable"
    return "NOT reachable -> " + ", ".join(_xy(cell) for cell in cells)


def _coherence(cells: Tuple[Cell, ...]) -> str:
    if not cells:
        return "OK (all shared walls match)"
    shown = ", ".join(_xy(cell) for cell in cells[:5])
    extra = "" if len(cells) <= 5 else f", ... (+{len(cells) - 5} more)"
    return f"{len(cells)} mismatching cell(s) -> {shown}{extra}"


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze an a_maze_ing output file: wall coherence and "
                    "whether the maze is perfect or a playable Pac-Man board.",
    )
    parser.add_argument("output_file", help="maze output file to analyze")
    parser.add_argument(
        "--min-loops", type=int, default=DEFAULT_MIN_LOOPS, metavar="N",
        help="independent routes a playable (non-perfect) maze must keep "
             "(default: %(default)s)",
    )
    parser.add_argument(
        "--max-dead-ends", type=int, default=DEFAULT_MAX_DEAD_ENDS,
        metavar="N",
        help="real dead-ends tolerated; use 0 for the no-dead-end bonus "
             "(default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    """読み込み・分析・報告を行い、プロセスの終了コードを返す。"""
    args = parse_args(argv)
    try:
        maze = Maze.from_file(args.output_file)
    except FileNotFoundError:
        print(f"Error: file not found: {args.output_file}")
        return EXIT_MALFORMED
    except (OSError, MazeError) as error:
        print(f"Malformed maze file: {error}")
        return EXIT_MALFORMED
    print(render(analyze(maze), args.min_loops, args.max_dead_ends))
    return EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as error:        # 予期しない入力でも安全に終了する
        print(f"Unexpected error while analyzing the maze: {error}")
        sys.exit(EXIT_MALFORMED)
