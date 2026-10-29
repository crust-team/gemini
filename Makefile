.PHONY: test test-release lint

test:
	python scripts/test_changed.py

test-release:
	python -m pytest -n auto -m "" --dataset=slow --profile=release --durations=20

lint:
	flake8 gemini tests examples scripts
	black --check gemini tests examples scripts
	isort --check-only gemini tests examples scripts
