#!/bin/bash

set -ex

flake8
mypy --check-untyped-defs pgsrip
pytest --cov-report term --cov-report html --cov pgsrip -vv tests