#!/bin/bash
# drive.sh <run id> <board> [--tfa X] [--optee X] [--uboot X] [--linux X] [--title T] [--requester R]
#
# The lease driver (docs/setup.md): the steps of run.yml in order, on one
# CIL lease, for a run whose pins are not all public (stage-trees.sh
# first). LAVA_TOKEN comes from the environment and is never printed.
# Leaves work/<run id>.json (the run document), work/out/ (builds, logs,
# packages). Resumable: a step whose output exists is not redone.
set -euo pipefail
[ $# -ge 2 ] || { sed -n '2p' "$0" >&2; exit 1; }
id=$1 board=$2; shift 2
title="" requester="lease-driver"; inputs=()
while [ $# -gt 0 ]; do
	case $1 in
	--tfa|--optee|--uboot|--linux) inputs+=("$1" "$2"); shift 2 ;;
	--title) title=$2; shift 2 ;;
	--requester) requester=$2; shift 2 ;;
	*) echo "unknown $1" >&2; exit 1 ;;
	esac
done
cd ~/oss-fw-ci
c() { sg docker -c "$(printf '%q ' env OSSCI_IMAGE=ossci-control:1 scripts/in-container.sh "$@")"; }
# The build and rootfs containers run code under test: no token in them.
b() { sg docker -c "$(printf '%q ' env -u LAVA_TOKEN -u PIN_BL2_RB3GEN2 OSSCI_IMAGE=ossci-build:1 scripts/in-container.sh "$@")"; }
r() { sg docker -c "$(printf '%q ' env -u LAVA_TOKEN -u PIN_BL2_RB3GEN2 OSSCI_IMAGE=ossci-rootfs:1 scripts/in-container.sh "$@")"; }
doc=work/$id.json
td=$(c python3 -m ossci.config top suite commit)
log() { echo "$(date -u +%FT%TZ) $*"; }
if [ ! -f "$doc" ]; then
	log resolve
	c python3 -m ossci.refs "work/$id.resolved.json" "${inputs[@]}"
	c python3 -m ossci.run new "$doc" --id "$id" --inputs "work/$id.resolved.json" --boards "$board" \
		--title "$title" --requester "$requester" --driver lease
fi
if [ ! -f work/out/rootfs/rootfs.json ]; then
	log rootfs
	r scripts/build-rootfs.sh arm64 "$td" work/out/rootfs /work/work/trees/qcom-buildroot
fi
c python3 -m ossci.run rootfs "$doc" work/out/rootfs/rootfs.json
c scripts/td-checkout.sh work/td
if [ ! -f "work/out/$id/$board.build.json" ] || grep -q '"error"' "work/out/$id/$board.build.json"; then
	log build
	fp=$(c python3 -c 'import json,sys; print([t["fingerprint"] for t in json.load(open(sys.argv[1]))["targets"] if t["board"]==sys.argv[2]][0])' "$doc" "$board")
	b scripts/build-board.sh "work/$id.resolved.json" "$board" "$fp" work/out/rootfs work/td "work/out/$id" || true
fi
c python3 -m ossci.run built "$doc" "$board" "work/out/$id/$board.build.json"
log submit
c python3 -m ossci.run submit "$doc" "work/out/$id" work/td
until c python3 -m ossci.run finished "$doc"; do
	c python3 -m ossci.run monitor "$doc" || log "monitor failed, retrying"
	c python3 -m ossci.run collect "$doc" ${OSSCI_BASELINE:+--baseline "$OSSCI_BASELINE"} || log "collect failed, retrying"
	c python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(" ".join("%s:%s:%s" % (t["board"], t["state"], (t.get("lava") or {}).get("job_id")) for t in d["targets"]))' "$doc"
	c python3 -m ossci.run finished "$doc" || sleep 300
done
log done
