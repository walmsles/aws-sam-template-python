export WORKDIR = $(shell pwd)

project = services
service_src = services

tests_src = tests
e2e_tests = $(tests_src)/e2e
int_tests = $(tests_src)/integration

all_src = $(service_src)

.PHONY: dev
dev:
	@pip install --upgrade pip pre-commit poetry > /dev/null
	@poetry install
	@pre-commit install

.PHONY: tests
tests:
	@poetry run pytest --ignore $(e2e_tests) --ignore $(int_tests) --cov=$(project) --cov-report=xml --cov-report term

.PHONY: format
format:
	@poetry run isort --profile black $(all_src)
	@poetry run black $(all_src)

.PHONY: lint
lint: format
	@poetry run flake8 $(all_src)

.PHONY: start-local
start-local: build
	@sam local start-api

.PHONY: pre-commit
pre-commit:
	@pre-commit run --show-diff-on-failure

.PHONY: synth
build: deps
	@poetry run sam build --use-container

.PHONY: guided
guided: deps build
	@poetry run sam deploy --guided

.PHONY: deploy
deploy: deps build
	@poetry run sam deploy

.PHONY: deploy/remove
deploy/remove:
	@poetry run sam delete

.PHONY: deps
deps:
	@scripts/make-deps.sh

.PHONY: clean
clean:
	@rm -rf .vscode .pytest_cache .coverage coverage.xml .mypy_cache .aws-sam
	@find services -type f -name "requirements.txt" -delete
	@find services tests -type d -name "__pycache__" -delete
	@poetry env remove --all > /dev/null
