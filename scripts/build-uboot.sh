#!/bin/bash
# build-uboot.sh <board> <u-boot tree> <fingerprint> <out dir>: U-Boot for
# the board (boards.yaml uboot), -<fingerprint> as LOCALVERSION.
# Out: u-boot.bin, u-boot.config, uboot.json.
set -euo pipefail
[ $# -eq 4 ] || { sed -n '2p' "$0" >&2; exit 1; }
board=$1 src=$(realpath "$2") fp=$3 out=$4
repo=$(cd "$(dirname "$0")/.." && pwd)
cfg() { (cd "$repo" && python3 -m ossci.config get "$board" "$1"); }
mkdir -p "$out"; out=$(realpath "$out")
b=$out/uboot-build
rm -rf "$b"
mapfile -t configs < <(cfg uboot.configs)
{ make -C "$src" O="$b" "${configs[@]}" &&
  make -C "$src" O="$b" -j"$(nproc)" LOCALVERSION="-$fp" DEVICE_TREE="$(cfg uboot.device_tree)"; } \
	> "$out/uboot.log" 2>&1 || { tail -40 "$out/uboot.log" >&2; exit 1; }
cp "$b/u-boot.bin" "$out/u-boot.bin"
cp "$b/.config" "$out/u-boot.config"
grep -aq -- "-$fp" "$out/u-boot.bin" || { echo "U-Boot lacks $fp" >&2; exit 1; }
rm -rf "$b"
printf '{"fingerprint": "%s", "commit": "%s", "u-boot.bin": "%s", "warnings": %d}\n' "$fp" \
	"$(git -C "$src" rev-parse HEAD)" "$(sha256sum "$out/u-boot.bin" | cut -d' ' -f1)" \
	"$(grep -c 'warning:' "$out/uboot.log" || true)" > "$out/uboot.json"
cat "$out/uboot.json"
