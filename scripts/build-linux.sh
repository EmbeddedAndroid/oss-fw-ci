#!/bin/bash
# build-linux.sh <board> <linux tree> <fingerprint> <out dir>: the kernel
# for the board: its config (boards.yaml linux.config) through
# olddefconfig, -<fingerprint> as LOCALVERSION (so /proc/version carries
# it), Image and the board DTB. Out: Image, board.dtb, linux.config,
# linux.json.
set -euo pipefail
[ $# -eq 4 ] || { sed -n '2p' "$0" >&2; exit 1; }
board=$1 src=$(realpath "$2") fp=$3 out=$4
repo=$(cd "$(dirname "$0")/.." && pwd)
cfg() { (cd "$repo" && python3 -m ossci.config get "$board" "$1"); }
mkdir -p "$out"; out=$(realpath "$out")
b=$out/linux-build
rm -rf "$b" && mkdir -p "$b"
cp "$repo/$(cfg linux.config)" "$b/.config"
mk() { make -C "$src" O="$b" ARCH=arm64 CROSS_COMPILE="$CROSS_COMPILE" "$@"; }
{ mk olddefconfig && mk -j"$(nproc)" LOCALVERSION="-$fp" Image dtbs; } > "$out/linux.log" 2>&1 ||
	{ tail -40 "$out/linux.log" >&2; exit 1; }
release=$(mk -s LOCALVERSION="-$fp" kernelrelease)
case $release in *"-$fp") ;; *) echo "release $release does not carry $fp" >&2; exit 1 ;; esac
cp "$b/arch/arm64/boot/Image" "$out/Image"
cp "$b/arch/arm64/boot/dts/$(cfg linux.dtb)" "$out/board.dtb"
cp "$b/.config" "$out/linux.config"
rm -rf "$b"
printf '{"fingerprint": "%s", "commit": "%s", "release": "%s", "Image": "%s", "dtb": "%s", "warnings": %d}\n' \
	"$fp" "$(git -C "$src" rev-parse HEAD)" "$release" "$(sha256sum "$out/Image" | cut -d' ' -f1)" \
	"$(sha256sum "$out/board.dtb" | cut -d' ' -f1)" "$(grep -c 'warning:' "$out/linux.log" || true)" > "$out/linux.json"
cat "$out/linux.json"
