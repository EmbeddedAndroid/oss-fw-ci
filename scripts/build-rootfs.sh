#!/bin/bash
# build-rootfs.sh <arch> <test-definitions commit> <out dir> [<qcom-buildroot tree>]
#
# The pinned test rootfs (config/rootfs.yaml), built once per cache key
# (ossci.rootfs key): `repo init` of the pinned manifest, the `build`
# project replaced by the pinned qcom-buildroot commit (fetched, or the
# tree given, which must already be that commit), the tree checked
# pristine (ossci.rootfs check: no patch, no change), then the
# architecture's makefile `buildroot` target with the pinned make
# arguments. Nothing in the tree is touched. Out: rootfs.cpio.gz,
# rootfs.json (key, fingerprint, sha256, the manifest as synced),
# build.log. Runs in the rootfs container on an x86_64 host.
set -euo pipefail
[ $# -ge 3 ] || { sed -n '2p' "$0" >&2; exit 1; }
arch=$1 td=$2 out=$3 given=${4:-}
repo=$(cd "$(dirname "$0")/.." && pwd)
pin() { (cd "$repo" && python3 -m ossci.config top rootfs "$1"); }
mkdir -p "$out"; out=$(realpath "$out")
commit=$(pin commit)
fp=$(cd "$repo" && python3 -m ossci.rootfs fingerprint "$td" "$arch")
key=$(cd "$repo" && python3 -m ossci.rootfs key "$td" "$arch")
ws=${OSSCI_WORK:-$repo/work}/rootfs-ws
mkdir -p "$ws"
cd "$ws"
src=$(pin source.repo); [ "$src" = None ] && src=
if [ -n "$given" ]; then
	bundle=$given
elif [ -n "$src" ]; then
	bundle=
else
	echo "rootfs pin ${commit:0:12} is not public yet ($(pin source.note))" >&2; exit 3
fi
# The pinned manifest from the pinned commit itself.
qb=$ws/qcom-buildroot
if [ -n "$bundle" ]; then
	rm -rf "$qb"; git clone -q "$bundle" "$qb"
else
	rm -rf "$qb"; git init -q "$qb"; git -C "$qb" fetch -q origin "$src" "$commit" 2>/dev/null ||
		git -C "$qb" fetch -q "$src" "$commit"
fi
git -C "$qb" -c advice.detachedHead=false checkout -q --detach "$commit"
(cd "$repo" && python3 -m ossci.rootfs check "$qb") >&2
mkdir -p "$ws/manifest"
git -C "$qb" show "$commit:$(pin manifest)" > "$ws/manifest/kodiak.xml"
git -C "$qb" show "$commit:manifests/common.xml" > "$ws/manifest/common.xml"
# repo needs a manifest repository: a local one holding the two files,
# with the build project taken out (it is the pinned checkout).
mr=$ws/manifest-repo
rm -rf "$mr"; mkdir -p "$mr/manifests"
cp "$ws/manifest/common.xml" "$mr/manifests/common.xml"
python3 - "$ws/manifest/kodiak.xml" "$mr/default.xml" <<'PY'
import re, sys
x = open(sys.argv[1]).read()
x = re.sub(r'\s*<project path="build"[^>]*>.*?</project>', "", x, flags=re.S)
open(sys.argv[2], "w").write(x)
PY
git -C "$mr" init -q && git -C "$mr" add -A && git -C "$mr" commit -qm manifest
top=$ws/tree
# A fresh tree every time: a leftover one would carry another manifest.
rm -rf "$top"; mkdir -p "$top"; cd "$top"
repo init -q -u "$mr" -m default.xml --no-clone-bundle < /dev/null
repo sync -q -j8 --no-clone-bundle --fail-fast
repo manifest -r -o "$out/manifest-synced.xml"
rm -rf "$top/build"; git clone -q "$qb" "$top/build"; git -C "$top/build" checkout -q --detach "$commit"
(cd "$repo" && python3 -m ossci.rootfs check "$top/build") >&2
ln -sf "$(pin "arch.$arch.makefile")" "$top/build/Makefile"
mapfile -t args < <(cd "$repo" && python3 -m ossci.config top rootfs "arch.$arch.make_args")
issue=$(cd "$repo" && python3 -m ossci.config top rootfs "arch.$arch.issue")
issue=${issue//\{fingerprint\}/$fp}
cd "$top/build"
# The toolchains first, as qcom-buildroot's build instructions do.
{ make -j2 "${args[@]}" toolchains &&
  make -j"$(nproc)" "${args[@]}" BR2_TARGET_GENERIC_ISSUE="$issue" buildroot; } > "$out/build.log" 2>&1 ||
	{ tail -60 "$out/build.log" >&2; exit 1; }
# The build stages firmware and the model into untracked directories of
# the tree; nothing tracked may have changed.
rm -f "$top/build/Makefile"
(cd "$repo" && python3 -m ossci.rootfs check "$top/build" --tracked) >&2
cp "$top/$(pin "arch.$arch.output")" "$out/rootfs.cpio.gz"
python3 - "$out/rootfs.json" "$key" "$fp" "$(sha256sum "$out/rootfs.cpio.gz" | cut -d' ' -f1)" <<'PY'
import json, sys
k = json.loads(sys.argv[2])
json.dump({"key": k["id"], "fingerprint": sys.argv[3], "sha256": sys.argv[4], "makefile": k["makefile"],
           "make_args": k["make_args"], "manifest": {"file": k["manifest"], "synced": "manifest-synced.xml"},
           "qcom_buildroot": k["qcom_buildroot"], "test_definitions": k["test_definitions"], "arch": k["arch"]},
          open(sys.argv[1], "w"), indent=1)
PY
cat "$out/rootfs.json"
