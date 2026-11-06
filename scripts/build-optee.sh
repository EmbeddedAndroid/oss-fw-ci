#!/bin/bash
# build-optee.sh <board> <optee_os tree> <fingerprint> <out dir>: OP-TEE OS
# for the board (boards.yaml optee), the fingerprint as TEE_IMPL_VERSION.
# Out: tee-raw.bin, optee.json (sha256, warnings).
set -euo pipefail
[ $# -eq 4 ] || { sed -n '2p' "$0" >&2; exit 1; }
board=$1 src=$(realpath "$2") fp=$3 out=$4
repo=$(cd "$(dirname "$0")/.." && pwd)
cfg() { (cd "$repo" && python3 -m ossci.config get "$board" "$1"); }
mkdir -p "$out"; out=$(realpath "$out")
mapfile -t args < <(cfg optee.make)
b=$out/optee-build
rm -rf "$b"
make -C "$src" -j"$(nproc)" O="$b" PLATFORM="$(cfg optee.platform)" CFG_ARM64_core=y \
	CROSS_COMPILE="$CROSS_COMPILE" CROSS_COMPILE_core="$CROSS_COMPILE" CROSS_COMPILE_ta_arm64="$CROSS_COMPILE" \
	TEE_IMPL_VERSION="$fp" "${args[@]}" > "$out/optee.log" 2>&1 || { tail -40 "$out/optee.log" >&2; exit 1; }
cp "$b/core/tee-raw.bin" "$out/tee-raw.bin"
grep -aq "$fp" "$out/tee-raw.bin" || { echo "OP-TEE lacks $fp" >&2; exit 1; }
rm -rf "$b"
printf '{"fingerprint": "%s", "commit": "%s", "tee-raw.bin": "%s", "warnings": %d}\n' "$fp" \
	"$(git -C "$src" rev-parse HEAD)" "$(sha256sum "$out/tee-raw.bin" | cut -d' ' -f1)" \
	"$(grep -c 'warning:' "$out/optee.log" || true)" > "$out/optee.json"
cat "$out/optee.json"
