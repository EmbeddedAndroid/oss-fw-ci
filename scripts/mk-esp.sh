#!/bin/bash
# mk-esp.sh <board> <linux out dir> <rootfs.cpio.gz> <out dir>: the ESP the
# board boots: a UKI (systemd-boot stub) of the run's Image, the board DTB
# from the same build, the board command line and the pinned rootfs as
# initramfs, on a FAT image as EFI/BOOT/BOOTAA64.EFI (U-Boot's EFI boot
# manager boots the removable-media path). Out: efi.bin, esp.json.
set -euo pipefail
[ $# -eq 4 ] || { sed -n '2p' "$0" >&2; exit 1; }
board=$1 linux=$(realpath "$2") rootfs=$(realpath "$3") out=$4
repo=$(cd "$(dirname "$0")/.." && pwd)
cfg() { (cd "$repo" && python3 -m ossci.config get "$board" "$1"); }
mkdir -p "$out"; out=$(realpath "$out")
work=$(mktemp -d "${OSSCI_WORK:-$repo/work}/esp.XXXXXX")
trap 'rm -rf "$work"' EXIT
ukify build --linux="$linux/Image" --initrd="$rootfs" --devicetree="$linux/board.dtb" \
	--cmdline="$(cfg linux.cmdline)" --efi-arch=aa64 \
	--stub=/usr/lib/systemd/boot/efi/linuxaa64.efi.stub --output="$work/uki.efi" >/dev/null
case $(cfg lava.storage) in ufs) sector=4096 ;; *) sector=512 ;; esac
size=$(($(cfg package.esp_size_mb) * 1024 * 1024))
[ "$(stat -c %s "$work/uki.efi")" -lt $((size - 16 * 1024 * 1024)) ] || { echo "UKI too large for the ESP" >&2; exit 1; }
rm -f "$out/efi.bin"; truncate -s $size "$out/efi.bin"
mkfs.fat -F 32 -S $sector "$out/efi.bin" >/dev/null
mmd -i "$out/efi.bin" ::/EFI ::/EFI/BOOT
mcopy -i "$out/efi.bin" "$work/uki.efi" ::/EFI/BOOT/BOOTAA64.EFI
printf '{"uki": "%s", "efi.bin": "%s", "cmdline": "%s"}\n' "$(sha256sum "$work/uki.efi" | cut -d' ' -f1)" \
	"$(sha256sum "$out/efi.bin" | cut -d' ' -f1)" "$(cfg linux.cmdline)" > "$out/esp.json"
