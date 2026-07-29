#!/usr/bin/env sh
set -eu

PREFIX=/opt/opennet
CONFIG_DIR=/etc/opennet
UNIT_PATH=/etc/systemd/system/opennet.service
START_SERVICE=1

if [ "${1:-}" = "--no-start" ]; then
  START_SERVICE=0
elif [ "$#" -ne 0 ]; then
  echo "usage: sudo ./install.sh [--no-start]" >&2
  exit 2
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "run this installer as root: sudo ./install.sh" >&2
  exit 1
fi

command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required" >&2
  exit 1
}
command -v systemctl >/dev/null 2>&1 || {
  echo "systemd is required; use pip/pipx on systems without systemd" >&2
  exit 1
}

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WHEEL=$(find "$SCRIPT_DIR" -maxdepth 1 -type f -name 'opennet_protocol-*.whl' | head -n 1)
if [ -z "$WHEEL" ]; then
  echo "the OpenNet wheel is missing from this release bundle" >&2
  exit 1
fi

if ! id opennet >/dev/null 2>&1; then
  useradd --system --home-dir "$PREFIX" --shell /usr/sbin/nologin opennet
fi

install -d -m 0755 "$PREFIX" "$CONFIG_DIR"
python3 -m venv "$PREFIX/venv"
"$PREFIX/venv/bin/python" -m pip install --disable-pip-version-check "$WHEEL"

if [ ! -f "$CONFIG_DIR/opennet.env" ]; then
  install -m 0640 -o root -g opennet "$SCRIPT_DIR/opennet.env" \
    "$CONFIG_DIR/opennet.env"
fi
install -m 0644 "$SCRIPT_DIR/opennet.service" "$UNIT_PATH"
systemctl daemon-reload

if [ "$START_SERVICE" -eq 1 ]; then
  systemctl enable --now opennet.service
  systemctl --no-pager --full status opennet.service || true
else
  echo "installed without starting; run: sudo systemctl enable --now opennet"
fi

echo "OpenNet installed in $PREFIX"
echo "Configuration: $CONFIG_DIR/opennet.env"
