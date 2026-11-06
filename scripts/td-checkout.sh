#!/bin/bash
# td-checkout.sh <dir>: test-definitions at the commit of config/suite.yaml.
set -euo pipefail
[ $# -eq 1 ] || { sed -n '2p' "$0" >&2; exit 1; }
repo=$(cd "$(dirname "$0")/.." && pwd)
top() { (cd "$repo" && python3 -m ossci.config top suite "$1"); }
dir=$1 commit=$(top commit)
if [ -d "$dir/.git" ] && [ "$(git -C "$dir" rev-parse HEAD)" = "$commit" ]; then exit 0; fi
rm -rf "$dir"; git init -q "$dir"
git -C "$dir" fetch -q --depth 1 "$(top repo)" "$commit"
git -C "$dir" checkout -q --detach "$commit"
