.PHONY: install run debug clean lint test build

SYSTEM_PYTHON = python3
VENV = .venv
PYTHON = $(VENV)/bin/python
CONFIG = config.txt

install: $(VENV)/.installed

$(VENV)/.installed: pyproject.toml
	$(SYSTEM_PYTHON) -m venv $(VENV)
	$(PYTHON) -m pip install ".[dev]"
	@touch $@

run:
	$(PYTHON) a_maze_ing.py $(CONFIG)

debug:
	$(PYTHON) -m pdb a_maze_ing.py $(CONFIG)

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache \) -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -prune -exec rm -rf {} +
	rm -rf build dist .coverage maze.txt $(VENV)

lint:
	$(PYTHON) -m flake8 .
	$(PYTHON) -m mypy . --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

test:
	$(PYTHON) -m pytest

build:
	$(PYTHON) -m build
