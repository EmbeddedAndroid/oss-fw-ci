#!/bin/bash
# site-checkout.sh <dir>: the gh-pages branch as a worktree at <dir> (an
# empty orphan branch when the remote has none yet). Run it through
# in-container.sh like publish-site.sh: git records the worktree by
# absolute path, which differs between the runner and the container.
set -euo pipefail
[ $# -eq 1 ] || { sed -n '2p' "$0" >&2; exit 1; }
site=$1
git worktree prune
if git fetch -q origin +gh-pages:refs/remotes/origin/gh-pages 2>/dev/null; then
	git worktree add -q --detach "$site" origin/gh-pages
else
	git worktree add -q --orphan -b gh-pages "$site"
fi
