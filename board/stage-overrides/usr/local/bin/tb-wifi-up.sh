#!/bin/sh
# TB710FU wifi bring-up: wpa_supplicant + busybox udhcpc with the broadcast bit.
#
# Why not NetworkManager: the campus DHCP server answers DHCP UNICAST to the
# offered address.  A client that has not yet configured that address cannot
# receive such a frame, so NM/udhcpc without -B never see the OFFER/ACK.
# busybox udhcpc has -B ("Request broadcast replies"), which makes the server
# answer 255.255.255.255 and the whole thing just works.
#
# Why not NM's DHCP: same reason, and NM also kept re-deactivating the device.
# So the wifi interface is unmanaged for NM (see 99-tb-wifi-unmanaged.conf).
#
# Credentials live in /etc/tb-wifi-credentials.conf (mode 600), NOT here:
#
#     SSID="your-network"
#     PSK="your-passphrase"
#
# This file ships with no credentials on purpose -- the image is built from a
# running system whose own credentials must not be published.

set -e
IFACE=wlp1s0
CRED=/etc/tb-wifi-credentials.conf
CONF=/etc/wpa_supplicant-tb.conf
LOG=/root/tb-wifi.log

log() { echo "$(date '+%F %T') $*" >> $LOG; }

case "$1" in
down)
    log "down: stopping udhcpc/wpa_supplicant"
    pkill -f 'udhcpc -i wlp1s0' 2>/dev/null || true
    pkill -f "wpa_supplicant.*$CONF" 2>/dev/null || true
    exit 0
    ;;
esac

if [ ! -f "$CRED" ]; then
    log "no $CRED -- wifi left unconfigured"
    echo "tb-wifi-up: $CRED is missing." >&2
    echo "Create it with SSID=\"...\" and PSK=\"...\" (chmod 600) and retry." >&2
    exit 1
fi
# shellcheck disable=SC1090
. "$CRED"
: "${SSID:?tb-wifi-up: set SSID= in $CRED}"
: "${PSK:?tb-wifi-up: set PSK= in $CRED}"

log "=== bring-up start ==="

# WiFi is soft-blocked at boot on this board (rfkill state file) and NM's radio
# is off by default.  Both must be undone before the interface exists.
rfkill unblock wifi 2>/dev/null || true
iw reg set CN 2>/dev/null || true

# wait for the driver to register phy0 (cold boot takes ~110 s)
i=0
while [ $i -lt 90 ]; do
    [ -d /sys/class/ieee80211/phy0 ] && break
    sleep 2
    i=$((i + 1))
done
[ -d /sys/class/ieee80211/phy0 ] || { log "phy0 never appeared"; exit 1; }
log "phy0 present after $((i * 2))s"

ip link set "$IFACE" up 2>/dev/null || true

cat > "$CONF" <<EOF
ctrl_interface=/var/run/wpa_supplicant
update_config=1
country=CN
ap_scan=1
network={
  ssid="$SSID"
  psk="$PSK"
  key_mgmt=WPA-PSK
  scan_ssid=1
}
EOF
chmod 600 "$CONF"

pkill -f "wpa_supplicant.*$CONF" 2>/dev/null || true
sleep 1
setsid wpa_supplicant -B -i "$IFACE" -c "$CONF" >> /root/wpa_supplicant-tb.log 2>&1 < /dev/null
log "wpa_supplicant started"

i=0
while [ $i -lt 40 ]; do
    if iw dev "$IFACE" link 2>/dev/null | grep -q 'Connected to'; then
        log "associated after $((i * 2))s: $(iw dev $IFACE link | sed -n 's/.*SSID: //p')"
        break
    fi
    sleep 2
    i=$((i + 1))
done
if ! iw dev "$IFACE" link 2>/dev/null | grep -q 'Connected to'; then
    log "association TIMEOUT"
    exit 1
fi

ip addr flush dev "$IFACE" 2>/dev/null || true
# -B is the whole point: ask for broadcast replies
setsid busybox udhcpc -i "$IFACE" -B -T 5 -t 10 -b -p /run/udhcpc-tb.pid \
       -s /usr/share/udhcpc/default.script >> /root/udhcpc-tb.log 2>&1 < /dev/null
log "udhcpc started (with -B)"

i=0
while [ $i -lt 30 ]; do
    if ip -4 addr show "$IFACE" 2>/dev/null | grep -q 'inet '; then
        log "lease ok: $(ip -4 -br addr show $IFACE)"
        ip route
        exit 0
    fi
    sleep 2
    i=$((i + 1))
done
log "no lease after 60s"
exit 1
