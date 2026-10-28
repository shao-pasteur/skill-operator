#!/usr/bin/env bash
# Copy a folder into a dated backup folder.
set -euo pipefail

src="${1:?usage: backup.sh <source-dir> <backup-root>}"
root="${2:?usage: backup.sh <source-dir> <backup-root>}"

dest="$root/$(date +%Y%m%d)"
mkdir -p "$dest"
cp -R "$src"/. "$dest"/
echo "backed up $src to $dest"
