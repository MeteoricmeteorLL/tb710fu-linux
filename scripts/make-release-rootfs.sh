#!/bin/bash
# TB710FU Linux rootfs -> sanitized, verified release tarball.
#
#   make-release-rootfs.sh [outdir] [overrides-dir]
#
# Sanitizing: the image is packed from a COPY of the running system, so the
# live machine is never modified.  Everything that identifies this particular
# device or its user -- wifi credentials, bluetooth pairings, browser profiles,
# ssh keys and shell history, logs, machine-id -- is left out, and a template
# is put in its place (see board/stage-overrides/ and tb-firstboot.service).
#
# Verification, because this board can silently corrupt memory: pages inside
# the bootloader's splash framebuffer (0xd5100000, 25 MiB) are handed out by
# the page allocator while the kernel's own boot console keeps drawing into
# them, so a large file can come back with different contents than were
# written.  See docs/KNOWN-ISSUES.md.  Until the DTB reserves that region the
# only way to ship a trustworthy tarball is to check it several ways:
#
#   1. manifest of the staged tree, twice, with the page cache dropped in
#      between -- a page scribbled between the reads shows up as a mismatch
#   2. zstd -t            the artifact matches its own content hash
#   3. decode twice       the decoded stream is stable across a cache drop
#   4. tar -d             every packed file compares equal to the staged tree
#   5. secret scan        the packed stream contains none of the live secrets
#
# Output: <outdir>/tb710fu-rootfs-<date>.tar.zst + .manifest.md5 + CHECKSUMS.txt
set -u

OUTDIR=${1:-/var/tmp/rel}
OVR=${2:-$OUTDIR/overrides}
STAMP=$(date +%Y%m%d)
NAME=tb710fu-rootfs-$STAMP
WORK=$OUTDIR/work
STAGE=$WORK/stage
OUT=$OUTDIR/$NAME.tar.zst
LOG=$OUTDIR/make-release-$STAMP.log

log()  { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
die()  { log "FATAL: $*"; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

[ "$(id -u)" = 0 ] || die "run as root"
for t in zstd python3 tar md5sum sha256sum find xargs grep; do
    have $t || die "missing $t"
done
[ -d "$OVR" ] || die "overrides dir $OVR missing (push board/stage-overrides/ first)"
df -Pk "$OUTDIR" | awk 'NR==2 { exit !($4 > 12*1024*1024) }' || die "need >12 GiB free in $OUTDIR"

# ------------------------------------------------------------------ secrets --
# Read the live credentials so the pack can prove they did not get in.  They
# are only used as grep patterns and are never written to the release.
SSID=$(sed -n 's/^[[:space:]]*SSID=//p' /usr/local/bin/tb-wifi-up.sh 2>/dev/null | head -1 | tr -d '"')
PSK=$(sed -n 's/^[[:space:]]*PSK=//p' /usr/local/bin/tb-wifi-up.sh 2>/dev/null | head -1 | tr -d '"')
[ -n "$SSID" ] || SSID=$(sed -n 's/^[[:space:]]*ssid="\(.*\)"/\1/p' /etc/wpa_supplicant-tb.conf 2>/dev/null | head -1)
[ -n "$PSK" ]  || PSK=$(sed -n 's/^[[:space:]]*psk="\(.*\)"/\1/p' /etc/wpa_supplicant-tb.conf 2>/dev/null | head -1)
log "live secrets to scan for: ssid=$([ -n "$SSID" ] && echo present || echo none) psk=$([ -n "$PSK" ] && echo present || echo none)"

# tar's own globs; kept in an array so the shell never expands them
EXC=( --one-file-system --warning=no-file-changed
 --exclude=./proc --exclude=./sys --exclude=./dev --exclude=./run
 --exclude=./tmp --exclude=./mnt --exclude=./media --exclude=./lost+found
 --exclude=./snap --exclude=./boot --exclude=./var/tmp
 --exclude=./var/cache --exclude=./var/crash --exclude=./var/log
 --exclude=./var/lib/apt/lists --exclude=./var/lib/snapd
 --exclude=./var/lib/bluetooth --exclude=./var/lib/NetworkManager
 --exclude=./var/lib/fwupd/pki
 --exclude=./var/lib/systemd/coredump --exclude=./var/lib/systemd/random-seed
 --exclude=./var/lib/dbus/machine-id --exclude=./var/lib/tb-firstboot.done
 --exclude=./usr/share/doc --exclude=./usr/share/man
 --exclude=./etc/netplan --exclude=./etc/machine-id --exclude='./etc/ssh/ssh_host_*'
 --exclude=./etc/NetworkManager/system-connections
 --exclude=./etc/wpa_supplicant-tb.conf --exclude=./etc/tb-wifi-credentials.conf
 --exclude=./root/.cache --exclude=./root/.ssh --exclude=./root/.presage
 --exclude=./root/.pki --exclude=./root/.dbus --exclude='./root/.*history'
 --exclude=./root/.wget-hsts --exclude=./root/.lesshst --exclude=./root/.viminfo
 --exclude=./root/.Xauthority --exclude='./root/.*errors' --exclude='./root/*.log'
 --exclude=./root/.mozilla --exclude=./root/.config/chromium
 --exclude=./root/.config/chromium-headless --exclude=./root/.config/falkon
 --exclude=./root/.local/share/falkon --exclude=./root/.local/share/Trash
 --exclude=./root/.local/share/baloo --exclude=./root/.local/share/kactivitymanagerd
 --exclude=./root/.local/share/klipper --exclude=./root/.local/share/konsole
 --exclude=./root/.local/share/kwalletd --exclude=./root/.local/share/flatpak
 --exclude=./root/.local/share/recently-used.xbel
 --exclude=./root/Desktop --exclude=./root/Documents --exclude=./root/Downloads
 --exclude=./root/Files --exclude=./root/Pictures --exclude=./root/Videos
 --exclude=./root/Music
 --exclude='./home/*/.ssh' --exclude='./home/*/.cache' --exclude='./home/*/.pki'
 --exclude='./home/*/.bash_history' --exclude='./home/*/.config/chromium' )

log "== 1/6 staging (a copy of the tree; the live system is not touched)"
rm -rf "$WORK"; mkdir -p "$STAGE"
tar --xattrs --xattrs-include='*' --numeric-owner "${EXC[@]}" -cf - -C / . \
    | tar --xattrs --xattrs-include='*' --numeric-owner -xpf - -C "$STAGE" \
    || die "staging failed"
sync
log "    staged $(du -sh "$STAGE" | cut -f1), $(find "$STAGE" -type f | wc -l) files"

log "== 2/6 sanitizing the copy"
cp -a "$OVR"/. "$STAGE"/ || die "copying overrides failed"
mkdir -p "$STAGE/etc/systemd/system/sysinit.target.wants"
ln -sf /etc/systemd/system/tb-firstboot.service \
       "$STAGE/etc/systemd/system/sysinit.target.wants/tb-firstboot.service"
chmod 755 "$STAGE/usr/local/bin/tb-firstboot.sh" "$STAGE/usr/local/bin/tb-wifi-up.sh"
chmod 600 "$STAGE/etc/tb-wifi-credentials.conf" "$STAGE/etc/wpa_supplicant-tb.conf"
: > "$STAGE/etc/machine-id"
mkdir -p "$STAGE/var/lib/dbus"; : > "$STAGE/var/lib/dbus/machine-id"

# Ownership.  The tree this packs was first staged on Windows at some point, which
# left "/" -- and 70-odd paths under it, including /usr and /etc -- owned by uid
# 197609 instead of root.  systemd then refuses to canonicalize any path below a
# non-root-owned parent ("unsafe path transition"), so systemd-tmpfiles silently
# creates nothing: /tmp/.X11-unix never appears, Xwayland cannot make its sockets,
# and every X11 application fails with "couldn't open display".  The 2 GB image
# published on 2026-10-06 had exactly this.  Normalize, and refuse to pack if it
# did not take.
chown 0:0 "$STAGE"
if find "$STAGE" -xdev \( -uid 197609 -o -gid 197609 \) -print -quit | grep -q .; then
    log "    paths owned by uid 197609 found -- normalizing"
    find "$STAGE" -xdev \( -uid 197609 -o -gid 197609 \) -exec chown 0:0 {} +
fi
[ "$(stat -c %u "$STAGE")" = 0 ] || die "staging root is owned by $(stat -c %u "$STAGE"), not root"
if find "$STAGE" -xdev \( -uid 197609 -o -gid 197609 \) -print -quit | grep -q .; then
    die "paths owned by uid 197609 survived normalization"
fi
log "    ownership normalized (root entry 0:0, no uid-197609 paths)"

for p in etc/ssh/ssh_host_rsa_key var/lib/bluetooth root/.ssh root/.bash_history \
         root/.config/chromium root/.cache etc/NetworkManager/system-connections \
         etc/wpa_supplicant-tb.conf; do
    case "$p" in
        etc/wpa_supplicant-tb.conf) continue ;;   # replaced by the template
    esac
    [ -e "$STAGE/$p" ] && die "sensitive path survived staging: $p"
done
log "    sensitive paths absent"

log "== 3/6 scanning the copy for secrets"
fail=0
for s in "$SSID" "$PSK"; do
    [ -n "$s" ] || continue
    hits=$(grep -rlF -- "$s" "$STAGE" 2>/dev/null | head -5)
    [ -z "$hits" ] || { log "    LEAK: '$s' found in $hits"; fail=1; }
done
# A private key outside the distro's own trees is a leak: the image's own keys
# (ssh host keys, fwupd's local signing key) were removed above, and anything
# under /usr/{lib,share,src} is a distro-shipped fixture that every install has.
# Debian's stock snakeoil cert is expected and is not machine-specific either.
# -I skips binaries: ssh, gpg, sshd and friends contain the PEM header as a
# string constant and are not keys.
keys=$(grep -rIl -- 'BEGIN .*PRIVATE KEY' "$STAGE" 2>/dev/null \
        | grep -v 'ssl-cert-snakeoil' \
        | grep -vE "^$STAGE/usr/(lib|share|src)/" \
        | head -8)
[ -z "$keys" ] || { log "    private keys left: $keys"; fail=1; }
[ $fail = 0 ] || die "sanitizing incomplete -- fix and re-run"
log "    clean"

log "== 4/6 manifest of the staged tree, twice, cache dropped in between"
manifest() { ( cd "$STAGE" && find . -type f -print0 | sort -z | xargs -0 md5sum ); }
manifest > "$WORK/m1.md5" || die "manifest 1 failed"
sync; echo 3 > /proc/sys/vm/drop_caches; sync
manifest > "$WORK/m2.md5" || die "manifest 2 failed"
if ! cmp -s "$WORK/m1.md5" "$WORK/m2.md5"; then
    diff "$WORK/m1.md5" "$WORK/m2.md5" | head -10 | tee -a "$LOG"
    die "the tree read back differently before and after a cache drop (RAM corruption while reading; see docs/KNOWN-ISSUES.md)"
fi
NFILES=$(wc -l < "$WORK/m1.md5")
log "    $NFILES files, identical across both reads"

attempt=0
while [ $attempt -lt 3 ]; do
    attempt=$((attempt + 1))
    log "== 5/6 packing, attempt $attempt: tar | zstd"
    rm -f "$OUT"
    if ! tar --xattrs --xattrs-include='*' --numeric-owner -cf - -C "$STAGE" . \
         | zstd -T0 -3 -q -f -o "$OUT"; then
        log "    compressor failed"; continue
    fi
    log "    wrote $(stat -c %s "$OUT") bytes"

    log "== 6/6 verifying"
    if ! zstd -t "$OUT" >/dev/null 2>&1; then
        log "    zstd -t FAILED: artifact does not match its own content hash"; continue
    fi
    log "    zstd -t ok"
    H1=$(zstd -dc "$OUT" | md5sum | cut -d' ' -f1)
    sync; echo 3 > /proc/sys/vm/drop_caches; sync
    H2=$(zstd -dc "$OUT" | md5sum | cut -d' ' -f1)
    if [ "$H1" != "$H2" ]; then
        log "    decoded stream not stable: $H1 vs $H2"; continue
    fi
    log "    decoded stream stable ($H1)"
    sync; echo 3 > /proc/sys/vm/drop_caches; sync
    zstd -dc "$OUT" | tar --xattrs --xattrs-include='*' -df - -C "$STAGE" \
        > "$WORK/tardiff.txt" 2>&1
    rc=$?
    if [ $rc -ne 0 ]; then
        log "    tar -d rc=$rc: packed content differs from the staged tree"
        head -10 "$WORK/tardiff.txt" | tee -a "$LOG"; continue
    fi
    log "    every packed file compares equal to the staged tree"
    log "    $(zstd -dc "$OUT" | tar -tf - | wc -l) members listed"
    leak=0
    for s in "$SSID" "$PSK"; do
        [ -n "$s" ] || continue
        n=$(zstd -dc "$OUT" | grep -a -c -F -- "$s" || true)
        if [ "${n:-0}" != 0 ]; then
            log "    LEAK in artifact: '$s' appears $n times"; leak=1
        fi
    done
    if [ $leak != 0 ]; then
        die "secret leaked into the artifact -- sanitizing is broken, not retrying"
    fi
    log "    secret scan clean"
    break
done
[ -f "$OUT" ] || die "packing failed after $attempt attempts"

SZ=$(stat -c %s "$OUT")
SHA=$(sha256sum "$OUT" | cut -d' ' -f1)
MD5=$(md5sum "$OUT" | cut -d' ' -f1)
cp -f "$WORK/m1.md5" "$OUTDIR/$NAME.manifest.md5"
cat > "$OUTDIR/CHECKSUMS.txt" <<EOF
# TB710FU Linux rootfs, $STAMP
file:          $NAME.tar.zst
size:          $SZ
sha256:        $SHA
md5:           $MD5
manifest:      $NAME.manifest.md5 ($NFILES files)
kernel:        $(uname -r)
built:         $(date -Is)
verified:      zstd -t; decoded stream identical across two cache drops;
               tar -d matched the staged tree file by file; secret scan clean
deploy:        see docs/DEPLOY.md
EOF
log "== done"
log "   artifact : $OUT"
log "   size     : $SZ"
log "   sha256   : $SHA"
log "   manifest : $OUTDIR/$NAME.manifest.md5 ($NFILES files)"
[ "${KEEP_STAGE:-0}" = 1 ] || rm -rf "$STAGE"
exit 0
