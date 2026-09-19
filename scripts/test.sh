#!/bin/bash

set -ex

uv run ruff check .
uv run ruff format --check .
uv run mypy pgsrip
uv run pytest --cov-report term --cov-report html --cov pgsrip -vv tests
