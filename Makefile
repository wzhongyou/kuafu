.PHONY: install dev test lint typecheck check clean

install:
	pip install -e .

dev:
	pip install -e ".[dev,web]"

test:
	pytest tests/ -v

lint:
	ruff check src/

typecheck:
	mypy src/

check: lint typecheck test

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
