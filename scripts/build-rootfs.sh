#!/bin/bash
# build-rootfs.sh <arch> <test-definitions commit> <out dir> [<qcom-buildroot tree>]
#
# The pinned test rootfs (config/rootfs.yaml), built once per cache key
# (ossci.rootfs key): `repo init` of the pinned manifest, the `build`
# project replaced by the pinned qcom-buildroot commit (fetched, or the
# tree given, which must already be that commit), the tree checked
# pristine (ossci.rootfs check: no patch, no change), then the
# architecture's makefile `buildroot` target with the pinned make
# arguments (a build stopped by a failed download is resumed, up to
# three tries). Nothing in the tree is touched. Out: rootfs.cpio.gz,
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
src=$(pin source.repo 2>/dev/null) || src=
[ "$src" = None ] && src=
[ -z "$src" ] && [ "$(pin upstream)" = True ] && src=$(pin repo)
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
overrides=$(cd "$repo" && python3 -c 'import json; from ossci import config; print(json.dumps({k: v["revision"] for k, v in (config.rootfs().get("manifest_overrides") or {}).items()}))')
python3 - "$ws/manifest/kodiak.xml" "$mr/default.xml" "$overrides" <<'PY'
import json, re, sys
x = open(sys.argv[1]).read()
x = re.sub(r'\s*<project path="build"[^>]*>.*?</project>', "", x, flags=re.S)
# An override is an <extend-project>: the manifest's own text is kept.
ext = "".join('  <extend-project name="%s" revision="%s" />\n' % (n, r) for n, r in json.loads(sys.argv[3]).items())
x = x.replace("</manifest>", ext + "</manifest>")
open(sys.argv[2], "w").write(x)
PY
git -C "$mr" init -q && git -C "$mr" add -A && git -C "$mr" commit -qm manifest
top=$ws/tree
if [ "${OSSCI_ROOTFS_RESUME:-}" = 1 ] && [ -f "$top/.ossci-key" ] && [ "$(cat "$top/.ossci-key")" = "$key" ]; then
	# The same key's interrupted build (killed, out of memory): Buildroot
	# carries on from its stamps.
	cd "$top"
	echo "resuming the build of this key in $top" >&2
else
	# A fresh tree otherwise: a leftover one would carry another manifest.
	rm -rf "$top"; mkdir -p "$top"; cd "$top"
	: > "$out/build.log"
	repo init -q -u "$mr" -m default.xml --no-clone-bundle < /dev/null
	repo sync -q -j8 --no-clone-bundle --fail-fast
	repo manifest -r -o "$out/manifest-synced.xml"
	rm -rf "$top/build"; git clone -q "$qb" "$top/build"; git -C "$top/build" checkout -q --detach "$commit"
	printf '%s' "$key" > "$top/.ossci-key"
	(cd "$repo" && python3 -m ossci.rootfs check "$top/build") >&2
fi
# A resumed tree has the staged build output; nothing tracked may differ.
(cd "$repo" && python3 -m ossci.rootfs check "$top/build" --tracked) >&2
ln -sf "$(pin "arch.$arch.makefile")" "$top/build/Makefile"
mapfile -t args < <(cd "$repo" && python3 -m ossci.config top rootfs "arch.$arch.make_args")
issue=$(cd "$repo" && python3 -m ossci.config top rootfs "arch.$arch.issue")
issue=${issue//\{fingerprint\}/$fp}
cd "$top/build"
# The toolchains first, as qcom-buildroot's build instructions do.
# Parallelism is a host knob, not part of the image: Buildroot builds
# packages side by side (per-package directories), and LLVM and Clang at
# full width each exhaust 32 GB, so the job levels stay below the CPUs.
jobs=${OSSCI_ROOTFS_JOBS:-8} jlevel=${OSSCI_BR2_JLEVEL:-12}
# Buildroot fetches each source once per site, and an upstream that
# drops connections (ffmpeg.org: wget exit 4 on 2 of 10 fetches) then
# fails the build; Buildroot resumes from its stamps, so a build that
# stopped on a download is run again, up to three times.
br() {
	make -j2 "${args[@]}" toolchains &&
	make -j"$jobs" "${args[@]}" BR2_JLEVEL="$jlevel" BR2_TARGET_GENERIC_ISSUE="$issue" buildroot
}
for try in 1 2 3; do
	mark=$(wc -l < "$out/build.log" 2>/dev/null || echo 0)
	br >> "$out/build.log" 2>&1 && break
	tail -n +"$((mark + 1))" "$out/build.log" | grep -q '/\.stamp_downloaded\] Error' && [ "$try" -lt 3 ] ||
		{ tail -60 "$out/build.log" >&2; exit 1; }
	echo "download failed (try $try), resuming in 60 s" >&2
	sleep 60
done
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
