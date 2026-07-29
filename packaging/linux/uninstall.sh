#!/usr/bin/env sh
set -eu

PURGE=0
if [ "${1:-}" = "--purge" ]; then
  PURGE=1
elif [ "$#" -ne 0 ]; then
  echo "usage: sudo ./uninstall.sh [--purge]" >&2
  exit 2
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "run this uninstaller as root: sudo ./uninstall.sh" >&2
  exit 1
fi

systemctl disable --now opennet.service 2>/dev/null || true
rm -f /etc/systemd/system/opennet.service
systemctl daemon-reload
rm -rf /opt/opennet

if [ "$PURGE" -eq 1 ]; then
  rm -rf /etc/opennet
  userdel opennet 2>/dev/null || true
else
  echo "preserved /etc/opennet; pass --purge to remove configuration and user"
fi
echo "OpenNet uninstalled"
