#!/bin/bash
# mk-rootfs-img.sh <board> <test-definitions tree> <out dir>: the rootfs
# partition image: ext4 with the test-definitions at /td (the commit of
# config/suite.yaml, checked), where the job's login mounts it
# (/lava-ovl) and LAVA writes its overlays. Out: rootfs.img.
set -euo pipefail
[ $# -eq 3 ] || { sed -n '2p' "$0" >&2; exit 1; }
board=$1 td=$(realpath "$2") out=$3
repo=$(cd "$(dirname "$0")/.." && pwd)
cfg() { (cd "$repo" && python3 -m ossci.config get "$board" "$1"); }
want=$(cd "$repo" && python3 -m ossci.config top suite commit)
[ "$(git -C "$td" rev-parse HEAD)" = "$want" ] || { echo "test-definitions is not at $want" >&2; exit 1; }
[ -z "$(git -C "$td" status --porcelain)" ] || { echo "test-definitions tree is changed" >&2; exit 1; }
mkdir -p "$out"; out=$(realpath "$out")
stage=$(mktemp -d "${OSSCI_WORK:-$repo/work}/rootfs-img.XXXXXX")
trap 'rm -rf "$stage"' EXIT
git -C "$td" archive --prefix=td/ HEAD | tar -x -C "$stage"
rm -f "$out/rootfs.img"
case $(cfg lava.storage) in ufs) bs=4096 ;; *) bs=1024 ;; esac
mke2fs -q -t ext4 -b $bs -L rootfs -d "$stage" "$out/rootfs.img" "$(cfg package.rootfs_size_mb)M"
