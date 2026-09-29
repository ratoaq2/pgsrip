#!/bin/bash
# Record docs/images/demo.gif with VHS in a container.
# Usage: scripts/demo.sh DIR
# DIR must contain only the media file that scripts/demo.tape uses. See the demo-gif skill.

set -e

# Git Bash: do not change the container paths into Windows paths
export MSYS_NO_PATHCONV=1

dir=$(cd "$1" && pwd -W 2>/dev/null || pwd)
repo=$(pwd -W 2>/dev/null || pwd)
engine=$(command -v podman || command -v docker)

"$engine" build -q -t localhost/pgsrip:latest .
"$engine" build -q -t localhost/pgsrip-vhs -f scripts/demo.Dockerfile .
"$engine" run --rm -v "$dir:/demo" -v "$repo:/repo" -w /repo localhost/pgsrip-vhs scripts/demo.tape
