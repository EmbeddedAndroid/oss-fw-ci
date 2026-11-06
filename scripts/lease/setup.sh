#!/bin/bash
# setup.sh: provision a fresh ubuntu-24.04 CIL VM as the lease driver of
# oss-fw-ci (docs/setup.md). Expects the repository at ~/oss-fw-ci (rsync
# from the laptop checkout, which stays authoritative). Installs docker,
# masks the apt timers (an unattended upgrade mid-build breaks docker),
# builds the three images.
set -euo pipefail
sudo systemctl mask --now apt-daily.timer apt-daily-upgrade.timer unattended-upgrades.service > /dev/null 2>&1 || true
sudo DEBIAN_FRONTEND=noninteractive apt-get -qq update
sudo DEBIAN_FRONTEND=noninteractive apt-get -qq install -y docker.io python3 git rsync > /dev/null
sudo usermod -aG docker "$USER"
cd ~/oss-fw-ci
for t in control build rootfs; do
	sudo docker build --network host -q --target $t -t ossci-$t:1 docker > /dev/null
	echo "image ossci-$t:1 built"
done
mkdir -p ~/oss-fw-ci/work
echo SETUP-DONE
