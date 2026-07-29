# OpenNet Linux service bundle

This bundle installs a dedicated, unprivileged `opennet` service under
`/opt/opennet` and keeps its settings in `/etc/opennet/opennet.env`.

```sh
tar -xzf OpenNet-linux-0.1.1.tar.gz
cd OpenNet-linux-0.1.1
sudo ./install.sh
```

The default listener is loopback-only. Read the
[security guide](https://github.com/devkyato/OpenNet/blob/v0.1.1/docs/security.md)
before exposing it to a network. The complete
[service/TLS guide](https://github.com/devkyato/OpenNet/blob/v0.1.1/docs/linux-service.md)
shows a hardened remote setup. Use `sudo ./install.sh --no-start` to inspect or
customize the unit before it starts.

To remove the program while preserving configuration:

```sh
sudo ./uninstall.sh
```

Use `sudo ./uninstall.sh --purge` to also remove the configuration and service
account.
