#!/bin/bash
# in-container.sh <command...>: run a repository command in an oss-fw-ci
# container (image $OSSCI_IMAGE, default ossci-control:1), as the calling
# user, with the checkout at /work. Only the variables the commands use
# pass through; LAVA_TOKEN and the PIN_BL2_<BOARD> images are set only in
# the jobs of the lava-hw environment.
repo=$(cd "$(dirname "$0")/.." && pwd)
exec docker run --rm --network host -u "$(id -u):$(id -g)" \
	-e OSSCI_WORK=/work/work -e LAVA_TOKEN -e PIN_BL2_RB3GEN2 -e LAVA_MCP_URL \
	-v "$repo:/work" -w /work "${OSSCI_IMAGE:-ossci-control:1}" "$@"
