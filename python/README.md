# OpenNet for Python

The reference ONP/1 client and server for Raspberry Pi and backend systems.

```bash
python -m pip install \
  https://github.com/devkyato/OpenNet/releases/download/v0.1.1/opennet_protocol-0.1.1-py3-none-any.whl
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

The wheel is distributed through GitHub Releases for v0.1.1; it is not yet
published on the public PyPI index.
