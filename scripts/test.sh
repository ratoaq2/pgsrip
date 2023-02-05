#!/bin/bash

set -ex

flake8
mypy --check-untyped-defs pgsrip
