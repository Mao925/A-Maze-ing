*This project has been created as part of the 42 curriculum by mhashimo and yohsawa.*

# A-Maze-ing

## Description

設定ファイルから、再現可能な迷路を生成する Python プロジェクトです。各セルの
壁を16進数で保存し、端末では ASCII 迷路として確認できます。完全迷路と、複数の
ループを持つ Pac-Man 風の迷路に対応しています。

## Instructions

```bash
cd submit
make install
make run
```

その他の Makefile ターゲットは次のとおりです。

```bash
make debug  # pdb で実行
make test   # pytest を実行
make lint   # flake8 と mypy を実行
make build  # 配布用パッケージを build/ と dist/ に作成
make clean  # キャッシュ、仮想環境、生成物を削除
```

または依存パッケージなしで、直接実行できます。

```bash
python3 a_maze_ing.py config.txt
```

実行後、`OUTPUT_FILE` で指定した場所に迷路が保存されます。対話可能な端末では
`1`（再生成）、`2`（最短経路の表示切替）、`3`（壁色の変更）、`4`（終了）が
使えます。リダイレクトやCIでは、迷路を1回表示して終了します。

### config.txt の形式

空行と `#` で始まるコメント行は無視されます。必須キーは次のとおりです。

```text
WIDTH=20
HEIGHT=15
ENTRY=0,0
EXIT=19,14
OUTPUT_FILE=maze.txt
PERFECT=false
SEED=42
```

`WIDTH` と `HEIGHT` は1以上の整数、`ENTRY` と `EXIT` は `x,y` 座標です。
`PERFECT` は `true` または `false`、`SEED` は任意の整数です。同じシードと設定なら
同じ迷路が得られます。`SEED` を省略した場合はランダムな迷路になります。

`OUTPUT_FILE` が相対パスの場合は、設定ファイルを基準に出力されます。

## Output format

1セルを16進数1文字で表します。ビットが1なら壁は閉鎖です：北=1、東=2、南=4、西=8。
迷路本体の後の空行に続けて、入口、出口、最短経路（`NESW` の連続文字列）を書きます。

生成結果は付属の解析ツールでも確認できます。

```bash
make run
python3 maze_analyzer.py maze.txt
```

## Reusable generator

生成器は `mazegen` パッケージとしても使えます。

```python
from mazegen import MazeGenerator

maze = MazeGenerator(width=20, height=15, seed=42)
maze.generate(perfect=False, protected_cells=frozenset({(0, 0), (19, 14)}))
path = maze.shortest_path((0, 0), (19, 14))
mask = maze.wall_mask((0, 0))
```

`wall_mask((x, y))` は壁ビット、`bl maze_analyzer.py   ocked_cells` は `42` のために完全閉鎖された
セル集合を返します。CLI・表示側は、この公開API以外の内部状態を読みません。

## Algorithm

まず反復版 DFS（再帰バックトラッカー）で全セルを一度ずつつなぐ完全迷路を作ります。
これは「全セル連結・ループなし」を自然に満たし、シード付き乱数で再現できます。
非完全モードでは、3×3の開放領域を作らないことを確認しながら壁を追加で取り除き、
少なくとも2つの独立ループを作ります。最短経路の探索には BFS を使います。
完全に閉じたセルを使った `42` パターンは、迷路が小さく配置できない場合を除き、
通常の通路と分離して生成されます。

## Team and project management

| 担当 | 内容 |
| --- | --- |
| mhashimo | `MazeGenerator`、DFS/BFS、壁整合性、42、迷路の検証とテスト |
| yohsawa  | 設定パーサー、CLI、保存、ASCII表示、Makefile、配布設定、文書 |

最初に座標を `(x, y)`、壁ビットを N=1/E=2/S=4/W=8 と合意しました。担当間の境界は
`MazeGenerator` の公開APIに固定し、CLIが内部グリッドに依存しないようにしました。
今後は小さい設定ファイルを増やし、実機端末で表示操作を確認するのが改善点です。

## Resources

- Python documentation: `random.Random`, `collections.deque`, `pathlib`
- 42 A-Maze-ing subject and provided `maze_analyzer.py`
- AI assistance: 初学者向けのコメント、設定パーサーとASCII表示のたたき台作成に使用。
  提出前にチームでコードを読み、テスト・lint・analyzerで確認します。
