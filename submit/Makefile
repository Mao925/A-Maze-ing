.PHONY: install run debug clean lint test build

PYTHON = python3
CONFIG = config.txt

install:
	$(PYTHON) -m pip install -e .[dev]

run:
	$(PYTHON) a_maze_ing.py $(CONFIG)

debug:
	$(PYTHON) -m pdb a_maze_ing.py $(CONFIG)

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache \) -prune -exec rm -rf {} +
	rm -rf build dist *.egg-info

lint:
	$(PYTHON) -m flake8 .
	$(PYTHON) -m mypy . --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

test:
	$(PYTHON) -m pytest

build:
	$(PYTHON) -m build
