export WORKDIR = $(shell pwd)

project = services
service_src = services
tests_src = tests

all_src = $(service_src)

.PHONY: dev
dev:
	pip install --upgrade pip pre-commit poetry
	poetry install
	pre-commit install

.PHONY: format
format:
	poetry run isort --profile black $(all_src)
	poetry run black $(all_src)

.PHONY: lint
lint: format
	poetry run flake8 $(all_src)

.PHONY: pre-commit
pre-commit:
	pre-commit run --show-diff-on-failure

.PHONY: synth
build: deps
	poetry run sam build 

.PHONY: guided
guided: deps build
	poetry run sam deploy --guided

.PHONY: deploy
deploy: deps build
	poetry run sam deploy

.PHONY: deploy/remove
deploy/remove:
	poetry run sam delete

.PHONY: deps
deps:
	scripts/make-deps.sh

.PHONY: clean
clean:
	rm -rf .vscode .pytest_cache .coverage coverage.xml .mypy_cache
	find services -type f -name "requirements.txt" -delete
	find services tests -type d -name "__pycache__" -exec rm -rf {} \;
	poetry env remove --all
