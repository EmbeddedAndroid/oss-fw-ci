#!/bin/bash
# build-board.sh <resolved.json> <board> <fingerprint> <rootfs dir> <test-definitions tree> <out dir>
#
# Everything one board flashes, from the run's inputs: each component in
# its own step with its own log (OP-TEE, U-Boot, Linux, then TF-A and the
# FIP around them), the ESP (Linux + the pinned rootfs), the rootfs
# partition image, and the package <out>/<board>.qcomflash.tar.gz with
# the BL2 deferred to the submit job. <out>/<board>.build.json records
# each component's fingerprint, commit, image sha256 and warnings; a
# failed step leaves "error" there and no package. Runs in the build
# container.
set -euo pipefail
[ $# -eq 6 ] || { sed -n '2,3p' "$0" >&2; exit 1; }
resolved=$(realpath "$1") board=$2 fp=$3 rootfs=$(realpath "$4") td=$(realpath "$5") out=$6
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$out"; out=$(realpath "$out")
w=$out/$board
mkdir -p "$w"
src=${OSSCI_WORK:-$here/../work}/src
mkdir -p "$src"
status=$w/status
: > "$status"
step() {
	local name=$1; shift
	if ! "$@" >> "$w/steps.log" 2> "$w/$name.err"; then
		echo "$name: $(tail -1 "$w/$name.err")" >> "$status"
		return 1
	fi
}
ok=1
step checkout-optee "$here/checkout.sh" "$resolved" optee "$src/optee_os" &&
	step optee "$here/build-optee.sh" "$board" "$src/optee_os" "$fp" "$w" || ok=0
step checkout-uboot "$here/checkout.sh" "$resolved" uboot "$src/u-boot" &&
	step uboot "$here/build-uboot.sh" "$board" "$src/u-boot" "$fp" "$w" || ok=0
step checkout-linux "$here/checkout.sh" "$resolved" linux "$src/linux" &&
	step linux "$here/build-linux.sh" "$board" "$src/linux" "$fp" "$w" || ok=0
if [ $ok = 1 ]; then
	step checkout-tfa "$here/checkout.sh" "$resolved" tfa "$src/tf-a" &&
		step tfa "$here/build-tfa.sh" "$board" "$src/tf-a" "$fp" "$w/tee-raw.bin" "$w/u-boot.bin" "$w" || ok=0
fi
if [ $ok = 1 ]; then
	step esp "$here/mk-esp.sh" "$board" "$w" "$rootfs/rootfs.cpio.gz" "$w" &&
		step rootfs-img "$here/mk-rootfs-img.sh" "$board" "$td" "$w" &&
		step package bash -c 'cd "$1" && python3 -m ossci.package build "$2" "$3/fip.elf" "$3/efi.bin" "$3/rootfs.img" "$4/$2.qcomflash.tar.gz"' \
			_ "$here/.." "$board" "$w" "$out" || ok=0
fi
python3 - "$w" "$out/$board.build.json" "$status" "$out/$board.qcomflash.tar.gz" <<'PY'
import json, os, sys, hashlib
w, dest, status, pkg = sys.argv[1:5]
comp = {}
for name, f in (("optee", "optee.json"), ("uboot", "uboot.json"), ("linux", "linux.json"), ("tfa", "tfa.json"),
                ("esp", "esp.json")):
    p = os.path.join(w, f)
    if os.path.exists(p):
        comp[name] = json.load(open(p))
err = open(status).read().strip()
out = {"components": comp}
if err:
    out["error"] = err
elif os.path.exists(pkg):
    h = hashlib.sha256()
    with open(pkg, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    out["package"] = {"file": os.path.basename(pkg), "sha256": h.hexdigest(), "size": os.path.getsize(pkg)}
json.dump(out, open(dest, "w"), indent=1)
print(json.dumps(out))
PY
[ $ok = 1 ]
