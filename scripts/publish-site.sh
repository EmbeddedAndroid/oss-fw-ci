#!/bin/bash
# publish-site.sh <gh-pages worktree> <run doc>: the run document into
# results/, the pages, index.json rebuilt, committed and pushed. Nothing
# is committed when the document did not change (its "updated" stamp
# aside). When another run pushed first, the worktree is reset to the
# remote and the publish redone: the document is the only input.
set -euo pipefail
[ $# -eq 2 ] || { sed -n '2p' "$0" >&2; exit 1; }
site=$1 doc=$2
repo=$(cd "$(dirname "$0")/.." && pwd)
id=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["run"]["id"])' "$doc")
dest=$site/results/$id.json
same() {
	[ -f "$dest" ] && python3 - "$doc" "$dest" <<'PY'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
for d in (a, b):
    d["run"].pop("updated", None)
sys.exit(0 if a == b else 1)
PY
}
publish() {
	touch "$site/.nojekyll"
	(cd "$repo" && python3 -m ossci.site "$site" "$doc")
	git -C "$site" add -A
	git -C "$site" -c user.name=oss-fw-ci -c user.email=oss-fw-ci@users.noreply.github.com \
		commit -q -m "results: $id"
}
same && exit 0
publish
for i in 1 2 3; do
	git -C "$site" push -q origin HEAD:gh-pages && exit 0
	git -C "$site" fetch -q origin +gh-pages:refs/remotes/origin/gh-pages
	git -C "$site" reset -q --hard origin/gh-pages
	publish
done
exit 1
