# Linux and Raspberry Pi service

The release bundle supports systemd systems with Python 3.9+ and the standard
library `venv` module.

## Install

```sh
grep 'OpenNet-linux-0.2.2.tar.gz' SHA256SUMS | sha256sum -c -
tar -xzf OpenNet-linux-0.2.2.tar.gz
cd OpenNet-linux-0.2.2
sudo ./install.sh
```

The installer creates:

- `/opt/opennet/venv` with the bundled wheel;
- an unprivileged `opennet` system account;
- `/etc/opennet/opennet.env`;
- `/etc/systemd/system/opennet.service`.

The default listener is `127.0.0.1:8765`. It can be used immediately by local
applications and is not reachable from another machine.

## Configure verified TLS for a LAN

Install certificates readable by the service:

```sh
sudo install -d -m 0750 -o root -g opennet /etc/opennet/tls
sudo install -m 0640 -o root -g opennet server.crt server.key \
  /etc/opennet/tls/
```

Create a systemd override:

```sh
sudo systemctl edit opennet
```

```ini
[Service]
ExecStart=
ExecStart=/opt/opennet/venv/bin/opennet serve --host 0.0.0.0 --tls-cert /etc/opennet/tls/server.crt --tls-key /etc/opennet/tls/server.key
```

Then:

```sh
sudo systemctl daemon-reload
sudo systemctl restart opennet
sudo systemctl status opennet
```

For mutual TLS, install the device CA and append
`--tls-client-ca /etc/opennet/tls/devices-ca.crt`.

## Operate and upgrade

```sh
journalctl -u opennet -f
systemctl show opennet -p ActiveState -p SubState -p NRestarts
```

To upgrade, extract the new bundle and rerun `sudo ./install.sh`; the installer
preserves `/etc/opennet/opennet.env`. Review release notes and restart the service.

To remove code while keeping configuration, run `sudo ./uninstall.sh`. Use
`sudo ./uninstall.sh --purge` only when the configuration and service account
should also be removed.
