#!/bin/bash
# build-tfa.sh <board> <tf-a tree> <fingerprint> <tee-raw.bin> <u-boot.bin> <out dir>:
# TF-A BL31 for the board (boards.yaml tfa) with the fingerprint as
# BUILD_STRING, the FIP of BL31 + OP-TEE + U-Boot, and fip.elf: the FIP
# wrapped at the board's load address and test-signed with the pinned
# qtestsign (no secret), which the pinned BL2 loads from uefi_a/uefi_b.
# The BL2 this tree builds is not used: the board's BL2 is pinned.
# Out: fip.bin, fip.elf, bl31.bin, tfa.json.
set -euo pipefail
[ $# -eq 6 ] || { sed -n '2p' "$0" >&2; exit 1; }
board=$1 src=$(realpath "$2") fp=$3 bl32=$(realpath "$4") bl33=$(realpath "$5") out=$6
repo=$(cd "$(dirname "$0")/.." && pwd)
cfg() { (cd "$repo" && python3 -m ossci.config get "$board" "$1"); }
top() { (cd "$repo" && python3 -m ossci.config top project "$1"); }
mkdir -p "$out"; out=$(realpath "$out")
b=$out/tfa-build
rm -rf "$b"
mapfile -t args < <(cfg tfa.make)
make -C "$src" -j"$(nproc)" BUILD_BASE="$b" CROSS_COMPILE="$CROSS_COMPILE" "${args[@]}" \
	BUILD_STRING="$fp" BL32="$bl32" BL33="$bl33" bl31 fip > "$out/tfa.log" 2>&1 ||
	{ tail -40 "$out/tfa.log" >&2; exit 1; }
fip=$(find "$b" -path "*/release/fip.bin" -o -path "*/debug/fip.bin" | head -1)
[ -n "$fip" ] || { echo "no fip.bin built" >&2; exit 1; }
bl31=$(dirname "$fip")/bl31.bin
cp "$fip" "$out/fip.bin"; cp "$bl31" "$out/bl31.bin"
grep -aq "$fp" "$out/bl31.bin" || { echo "BL31 lacks $fp" >&2; exit 1; }
[ "$(grep -ac "$fp" "$out/fip.bin")" -ge 3 ] || { echo "FIP lacks $fp in BL31, OP-TEE or U-Boot" >&2; exit 1; }
qts=$out/qtestsign
rm -rf "$qts"
git init -q "$qts"
git -C "$qts" fetch -q --depth 1 "$(top qtestsign.repo)" "$(top qtestsign.commit)"
git -C "$qts" checkout -q --detach FETCH_HEAD
wrap=$out/wrap
rm -rf "$wrap" && mkdir -p "$wrap" && ln -s "$qts" "$wrap/qtestsign"
(cd "$wrap" && "$src/tools/qti/generate_fip_elf.sh" "$out/fip.bin" "$(cfg tfa.fip_load_addr)") >> "$out/tfa.log" 2>&1 ||
	{ tail -20 "$out/tfa.log" >&2; exit 1; }
mv "$wrap/fip.elf" "$out/fip.elf"
rm -rf "$b" "$wrap" "$qts"
printf '{"fingerprint": "%s", "commit": "%s", "bl31.bin": "%s", "fip.elf": "%s", "warnings": %d}\n' "$fp" \
	"$(git -C "$src" rev-parse HEAD)" "$(sha256sum "$out/bl31.bin" | cut -d' ' -f1)" \
	"$(sha256sum "$out/fip.elf" | cut -d' ' -f1)" "$(grep -c 'warning:' "$out/tfa.log" || true)" > "$out/tfa.json"
cat "$out/tfa.json"
