#!/usr/bin/env python3

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from mazegen import Direction, MazeGenerator, Point


REQUIRED_KEYS = frozenset(
    {"WIDTH", "HEIGHT", "ENTRY", "EXIT", "OUTPUT_FILE", "PERFECT"}
)
ALLOWED_KEYS = REQUIRED_KEYS | {"SEED"}


class ConfigError(ValueError):
    """設定ファイルの内容を利用できないときに使う例外。"""


@dataclass(frozen=True)
class MazeConfig:
    """文字列だった設定値を、使いやすい型に変換した結果。"""

    width: int
    height: int
    entry: Point
    exit: Point
    output_file: Path
    perfect: bool
    seed: int | None


def parse_config(path: Path) -> MazeConfig:
    """``KEY=VALUE`` 形式の設定ファイルを読み、検証済み設定を返す。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ConfigError(f"Cannot read config file: {path} ({error})") from error

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        # 空行と # で始まる行は説明用なので、設定値ではありません。
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"Line {line_number}: use the KEY=VALUE format")
        key, value = (part.strip() for part in line.split("=", maxsplit=1))
        if key not in ALLOWED_KEYS:
            raise ConfigError(f"Line {line_number}: unknown key: {key}")
        if not value:
            raise ConfigError(f"Line {line_number}: {key} must not be empty")
        if key in values:
            raise ConfigError(f"Line {line_number}: duplicate key: {key}")
        values[key] = value

    missing = REQUIRED_KEYS - values.keys()
    if missing:
        raise ConfigError(f"Missing required key(s): {', '.join(sorted(missing))}")

    width = parse_positive_int(values["WIDTH"], "WIDTH")
    height = parse_positive_int(values["HEIGHT"], "HEIGHT")
    entry = parse_point(values["ENTRY"], "ENTRY")
    exit_point = parse_point(values["EXIT"], "EXIT")
    check_point_in_bounds(entry, "ENTRY", width, height)
    check_point_in_bounds(exit_point, "EXIT", width, height)
    if entry == exit_point:
        raise ConfigError("ENTRY and EXIT must be different points")

    # 相対パスは config.txt があるフォルダから見た場所として扱います。
    output_file = Path(values["OUTPUT_FILE"])
    if not output_file.is_absolute():
        output_file = path.parent / output_file
    seed = parse_int(values["SEED"], "SEED") if "SEED" in values else None
    return MazeConfig(
        width=width,
        height=height,
        entry=entry,
        exit=exit_point,
        output_file=output_file,
        perfect=parse_bool(values["PERFECT"]),
        seed=seed,
    )


def parse_int(text: str, name: str) -> int:
    """整数文字列を int に変換し、失敗時は設定向けの説明を返す。"""
    try:
        return int(text)
    except ValueError as error:
        raise ConfigError(f"{name} must be an integer: {text!r}") from error


def parse_positive_int(text: str, name: str) -> int:
    """1以上の整数を読む。幅と高さに使う。"""
    number = parse_int(text, name)
    if number < 1:
        raise ConfigError(f"{name} must be at least 1")
    return number


def parse_point(text: str, name: str) -> Point:
    """``x,y`` を座標タプル ``(x, y)`` に変換する。"""
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 2:
        raise ConfigError(f"{name} must use the x,y format: {text!r}")
    return (parse_int(parts[0], name), parse_int(parts[1], name))


def parse_bool(text: str) -> bool:
    """PERFECT に使う true / false を読み取る。"""
    normalized = text.lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ConfigError("PERFECT must be true or false")


def check_point_in_bounds(
    point: Point,
    name: str,
    width: int,
    height: int,
) -> None:
    """座標が迷路の中にあるか確認する。"""
    x, y = point
    if not 0 <= x < width or not 0 <= y < height:
        raise ConfigError(f"{name}={x},{y} is outside the {width}x{height} maze")


def write_maze(
    path: Path,
    maze: MazeGenerator,
    config: MazeConfig,
) -> list[str]:
    """迷路を課題指定の16進形式で保存し、最短経路も返す。"""
    path_steps = maze.shortest_path(config.entry, config.exit)
    grid_lines = [
        "".join(f"{maze.wall_mask((x, y)):X}" for x in range(maze.width))
        for y in range(maze.height)
    ]
    contents = "\n".join(
        grid_lines
        + [
            "",
            point_text(config.entry),
            point_text(config.exit),
            "".join(path_steps),
        ]
    ) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8", newline="\n")
    except OSError as error:
        raise ConfigError(f"Cannot write output file: {path} ({error})") from error
    return path_steps


def point_text(point: Point) -> str:
    """座標タプルを出力形式の ``x,y`` にする。"""
    return f"{point[0]},{point[1]}"


def path_cells(entry: Point, path_steps: list[str]) -> set[Point]:
    """移動列を、表示時に印を付けるセル集合へ変換する。"""
    steps = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
    x, y = entry
    cells = {entry}
    for step in path_steps:
        dx, dy = steps[step]
        x, y = x + dx, y + dy
        cells.add((x, y))
    return cells


def draw_maze(
    maze: MazeGenerator,
    config: MazeConfig,
    path_steps: list[str],
    show_path: bool,
    wall: str = "#",
) -> str:
    """公開APIだけを使って、端末用の ASCII 迷路を作る。"""
    marked = path_cells(config.entry, path_steps) if show_path else set()
    rows: list[str] = []
    for y in range(maze.height):
        # セル上側の横壁。各セルの北壁を3文字で描きます。
        rows.append("+" + "+".join(
            wall * 3 if maze.wall_mask((x, y)) & Direction.N else " " * 3
            for x in range(maze.width)
        ) + "+")
        middle = []
        for x in range(maze.width):
            point = (x, y)
            left = wall if maze.wall_mask(point) & Direction.W else " "
            if point in maze.blocked_cells:
                cell = "42 "
            elif point == config.entry:
                cell = " E "
            elif point == config.exit:
                cell = " X "
            elif point in marked:
                cell = " . "
            else:
                cell = "   "
            middle.extend([left, cell])
        last_cell = (maze.width - 1, y)
        right = wall if maze.wall_mask(last_cell) & Direction.E else " "
        rows.append("".join(middle) + right)
    rows.append("+" + "+".join(
        wall * 3
        if maze.wall_mask((x, maze.height - 1)) & Direction.S
        else " " * 3
        for x in range(maze.width)
    ) + "+")
    return "\n".join(rows)


def interactive_display(
    maze: MazeGenerator,
    config: MazeConfig,
    path_steps: list[str],
) -> None:
    """端末上で r（再生成）、p（経路）、c（壁）、q（終了）を受け付ける。"""
    show_path = True
    wall = "#"
    generation_number = 0
    while True:
        print(draw_maze(maze, config, path_steps, show_path, wall))
        command = input(
            "[r] regenerate  [p] show/hide path  [c] change walls  [q] quit > "
        ).strip().lower()
        if command == "q":
            return
        if command == "r":
            generation_number += 1
            # SEEDを固定した場合も r のたびに別の盤面になるよう、番号を足す。
            if config.seed is None:
                seed = None
            else:
                seed = config.seed + generation_number
            maze = MazeGenerator(config.width, config.height, seed)
            protected = frozenset({config.entry, config.exit})
            maze.generate(config.perfect, protected)
            path_steps = write_maze(config.output_file, maze, config)
            print(f"New maze saved to: {config.output_file}")
        elif command == "p":
            show_path = not show_path
        elif command == "c":
            wall = "*" if wall == "#" else "#"
        else:
            print("Please enter r, p, c, or q.")


def run(config_path: Path, output: TextIO = sys.stdout) -> int:
    """生成から保存・表示までを実行し、終了コードを返す。"""
    config = parse_config(config_path)
    maze = MazeGenerator(config.width, config.height, config.seed)
    maze.generate(config.perfect, frozenset({config.entry, config.exit}))
    path_steps = write_maze(config.output_file, maze, config)
    print(f"Maze saved to: {config.output_file}", file=output)
    if output is sys.stdout and sys.stdin.isatty():
        interactive_display(maze, config, path_steps)
    else:
        # CIやリダイレクト中には input() を呼ばず、1回表示して終了します。
        print(draw_maze(maze, config, path_steps, show_path=True), file=output)
    return 0


def main(arguments: list[str] | None = None) -> int:
    """コマンドライン引数を確認し、利用者向けのエラーを表示する。"""
    args = sys.argv[1:] if arguments is None else arguments
    if len(args) != 1:
        print("Usage: python3 a_maze_ing.py config.txt", file=sys.stderr)
        return 2
    try:
        return run(Path(args[0]))
    except (ConfigError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
