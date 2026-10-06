#!/bin/sh
# TB710FU first-boot setup.
#
# The published rootfs is a copy of a running system with everything that
# identifies that particular device taken out.  This service puts back the
# per-machine pieces, once, on the first boot of a fresh deployment:
#
#   * /etc/machine-id and /var/lib/dbus/machine-id (emptied before packing,
#     because they identify the machine the image was built on)
#   * ssh host keys (removed before packing; every deployment must have its
#     own, otherwise they all share one private key)
#   * a hostname
#   * an empty /etc/tb-wifi-credentials.conf so tb-wifi.service has something
#     to point the user at
#
# It then disables itself.
set -e
MARK=/var/lib/tb-firstboot.done
[ -e "$MARK" ] && exit 0

# --- machine-id ---
if [ ! -s /etc/machine-id ]; then
    rm -f /etc/machine-id
    systemd-machine-id-setup
    echo "tb-firstboot: machine-id = $(cat /etc/machine-id)"
fi
if [ -d /var/lib/dbus ] && [ ! -s /var/lib/dbus/machine-id ]; then
    ln -sf /etc/machine-id /var/lib/dbus/machine-id
fi

# --- ssh host keys ---
if ! ls /etc/ssh/ssh_host_*_key >/dev/null 2>&1; then
    ssh-keygen -A
    echo "tb-firstboot: ssh host keys generated"
fi

# --- hostname ---
if [ ! -s /etc/hostname ] || [ "$(cat /etc/hostname)" = "tb710fu" ]; then
    printf 'tb710fu\n' > /etc/hostname
    hostname tb710fu 2>/dev/null || true
    grep -q '^127\.0\.1\.1' /etc/hosts 2>/dev/null || \
        printf '127.0.1.1\ttb710fu\n' >> /etc/hosts
fi

# --- wifi credentials placeholder ---
if [ ! -e /etc/tb-wifi-credentials.conf ]; then
    cat > /etc/tb-wifi-credentials.conf <<'EOF'
# TB710FU wifi credentials -- fill these in for your own network, then
#   systemctl restart tb-wifi.service
# SSID="my-network"
# PSK="my-passphrase"
EOF
    chmod 600 /etc/tb-wifi-credentials.conf
fi

mkdir -p /var/lib
touch "$MARK"
systemctl disable tb-firstboot.service 2>/dev/null || true
echo "tb-firstboot: done"
