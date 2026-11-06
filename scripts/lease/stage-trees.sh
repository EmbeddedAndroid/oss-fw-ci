#!/bin/bash
# stage-trees.sh: on the lease, the trees whose pins are not public yet,
# from the bundles synced to ~/bundles (made on the laptop from its
# checkouts; their bases are public):
#   work/src/linux               kernel-topics 9226b98151 + linux-kodiak.bundle (b5e84377bb7a)
#   work/trees/qcom-buildroot    qcom-buildroot main 6bd87d7 + qcom-buildroot.bundle (79369f4)
# checkout.sh uses a tree already at the resolved commit as it is.
set -euo pipefail
cd ~/oss-fw-ci
mkdir -p work/src work/trees
stage() {
	local dir=$1 url=$2 base=$3 bundle=$4 ref=$5 want=$6
	if [ "$(git -C "$dir" rev-parse HEAD 2>/dev/null)" = "$want" ]; then echo "$dir ok"; return; fi
	rm -rf "$dir"; git init -q "$dir"
	git -C "$dir" fetch -q --depth 1 "$url" "$base"
	git -C "$dir" bundle verify -q "$bundle"
	git -C "$dir" fetch -q "$bundle" "$ref"
	git -C "$dir" checkout -q --detach "$want"
	echo "$dir $(git -C "$dir" rev-parse HEAD)"
}
stage work/src/linux https://github.com/qualcomm-linux/kernel-topics 9226b98151cf6fd0cc153e4680635f8b0723511c \
	~/bundles/linux-kodiak.bundle refs/heads/oss-fw-ci/kodiak-baseline b5e84377bb7a1d0390410c5d73620b340f6a9df9
stage work/trees/qcom-buildroot https://github.com/qualcomm-linux/qcom-buildroot 6bd87d78b36e48446635dd3567e0931903cb7525 \
	~/bundles/qcom-buildroot.bundle refs/heads/qcom-test-suite 79369f48964864906e522d024b76a30068599ea7
