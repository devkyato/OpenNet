# OpenNet for Python

The reference ONP/1 client and server I use for Raspberry Pi and backend
projects.

```bash
python -m pip install \
  https://github.com/devkyato/OpenNet/releases/download/v0.2.2/opennet_protocol-0.2.2-py3-none-any.whl
opennet serve
```

```python
import asyncio
from opennet import OpenNetClient

async def main():
    async with OpenNetClient("127.0.0.1") as client:
        await client.send("demo/message", {"hello": "OpenNet"}, retries=2)

asyncio.run(main())
```

The complete documentation, ESP32 Arduino library, examples, protocol
specification, and security guidance are in the
[OpenNet repository](https://github.com/devkyato/OpenNet).

The server also accepts an optional sync or async `authorizer`. It sees the
validated frame and the peer's TLS certificate before the handler or ACK, which
keeps topic rules in one explicit place. See
[Authorizing topics](https://github.com/devkyato/OpenNet/blob/v0.2.2/docs/authorization.md).

The wheel is distributed through GitHub Releases for v0.2.2; it is not yet
published on the public PyPI index.
