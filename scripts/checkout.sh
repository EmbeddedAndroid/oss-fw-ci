#!/bin/bash
# checkout.sh <resolved.json> <component> <dir>: the component's source at
# its resolved commit (ossci.refs), and for a lore input the series
# fetched with b4 and applied with git am on it. A tree already at that
# commit (a lease driver's staged bundle) is used as it is, after a check
# that it is clean. Prints the head commit.
set -euo pipefail
[ $# -eq 3 ] || { sed -n '2p' "$0" >&2; exit 1; }
resolved=$1 comp=$2 dir=$3
field() { python3 -c 'import json,sys; v=json.load(open(sys.argv[1]))[sys.argv[2]]
for k in sys.argv[3].split("."): v=(v or {}).get(k)
print(v or "")' "$resolved" "$comp" "$1"; }
repo=$(field repo) ref=$(field ref) commit=$(field commit) msgid=$(field series.message_id)
if [ -d "$dir/.git" ] && [ "$(git -C "$dir" rev-parse HEAD 2>/dev/null)" = "$commit" ]; then
	[ -z "$(git -C "$dir" status --porcelain --untracked-files=no)" ] || { echo "$dir is not clean" >&2; exit 1; }
else
	rm -rf "$dir"
	git init -q "$dir"
	git -C "$dir" remote add origin "$repo"
	# A commit by id where the server allows it, else through its ref.
	git -C "$dir" fetch -q --depth 1 origin "$commit" 2>/dev/null ||
		git -C "$dir" fetch -q --depth 1 origin "$ref"
	git -C "$dir" checkout -q --detach "$commit"
fi
if [ -n "$msgid" ]; then
	# A series needs history for git am's three-way fallback and for
	# checkpatch-like tools: deepen a little.
	git -C "$dir" fetch -q --deepen 50 origin "$commit" 2>/dev/null || true
	work=$(mktemp -d)
	(cd "$work" && b4 -q am -o "$work" -- "$msgid") >&2
	mbox=$(ls "$work"/*.mbx | head -1)
	git -C "$dir" -c user.name=ossci -c user.email=ossci@localhost am -q "$mbox"
	rm -rf "$work"
fi
git -C "$dir" rev-parse HEAD
