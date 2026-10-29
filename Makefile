.PHONY: test test-release lint

test:
	python scripts/test_changed.py

test-release:
	python -m pytest -n auto -m "" --dataset=slow --profile=release --durations=20

lint:
	flake8 gemini tests examples scripts docs/conf.py
	black --check gemini tests examples scripts docs/conf.py
	isort --check-only gemini tests examples scripts docs/conf.py
