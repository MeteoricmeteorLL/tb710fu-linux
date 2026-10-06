#!/bin/sh
# Verify a TB710FU rootfs download, and optionally the tree after deploying it.
#
#   verify-rootfs.sh <tb710fu-rootfs-*.tar.zst>          check the download
#   verify-rootfs.sh --deployed <mounted-rootfs> <manifest.md5>
#                                                        check the deployed tree
#
# The download check reads the whole artifact, so it takes a few minutes for
# 2 GB.  It compares sha256 (if release/CHECKSUMS.txt sits next to the tarball),
# then asks zstd to verify its own content hash, then lists the archive.
#
# The deployed check runs md5sum over every file in the manifest - 75 175 files
# on the shipped image - which is the only way to be sure the extraction was
# faithful.  Run it with a manifest that came with the release, not one from the
# tarball itself.
set -u

die() { echo "FAIL: $*" >&2; exit 1; }

if [ "${1:---help}" = "--deployed" ]; then
    root=${2:-}; man=${3:-}
    [ -d "$root" ] || die "usage: $0 --deployed <mounted-rootfs> <manifest.md5>"
    [ -f "$man" ] || die "manifest not found: $man"
    cd "$root" || die "cannot enter $root"
    echo "== md5 of every file in $man, under $root"
    if md5sum -c --quiet "$man"; then
        echo "OK: every file matches the manifest"
    else
        die "some files do not match - re-extract, and see docs/KNOWN-ISSUES.md §1"
    fi
    exit 0
fi

img=${1:-}
[ -f "$img" ] || die "usage: $0 <tb710fu-rootfs-*.tar.zst>"
command -v zstd >/dev/null || die "need zstd"

dir=$(dirname "$img")
base=$(basename "$img")

echo "== 1/4 sha256"
if [ -f "$dir/CHECKSUMS.txt" ]; then
    want=$(sed -n 's/^sha256:[[:space:]]*//p' "$dir/CHECKSUMS.txt" | head -1)
    got=$(sha256sum "$img" | cut -d' ' -f1)
    echo "   expected $want"
    echo "   actual   $got"
    [ "$want" = "$got" ] || die "sha256 mismatch: the download is damaged"
else
    echo "   no CHECKSUMS.txt beside the tarball - skipping"
    sha256sum "$img"
fi

echo "== 2/4 size"
sz=$(stat -c %s "$img" 2>/dev/null || stat -f %z "$img")
echo "   $sz bytes"
if [ -f "$dir/CHECKSUMS.txt" ]; then
    want=$(sed -n 's/^size:[[:space:]]*//p' "$dir/CHECKSUMS.txt" | head -1)
    [ "$want" = "$sz" ] || die "size mismatch (expected $want)"
fi

echo "== 3/4 zstd -t (the artifact's own content hash)"
zstd -t "$img" || die "zstd reports corruption - download it again"

echo "== 4/4 archive listing"
if [ -f "$dir/tb710fu-rootfs-$(echo "$base" | sed -n 's/^tb710fu-rootfs-\([0-9]*\)\.tar\.zst$/\1/p').manifest.md5" ]; then
    man="$dir/tb710fu-rootfs-$(echo "$base" | sed -n 's/^tb710fu-rootfs-\([0-9]*\)\.tar\.zst$/\1/p').manifest.md5"
    n_arch=$(zstd -dc "$img" | tar -tf - | wc -l)
    n_man=$(wc -l < "$man")
    echo "   $n_arch members in the archive, $n_man files in the manifest"
    zstd -dc "$img" | tar -tf - >/dev/null || die "tar cannot read the archive"
else
    zstd -dc "$img" | tar -tf - | head -5
    zstd -dc "$img" | tar -tf - | wc -l
fi

cat <<'EOF'

OK: the artifact is intact.
    Extract with:  zstd -dc <img> | sudo tar --xattrs --numeric-owner -xpf - -C <mnt>
    Then check the result:  verify-rootfs.sh --deployed <mnt> <manifest.md5>
    Deployment: docs/DEPLOY.md
EOF
