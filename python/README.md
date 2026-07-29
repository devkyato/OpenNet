# OpenNet for Python

The reference ONP/1 client and server for Raspberry Pi and backend systems.

```bash
python -m pip install opennet-protocol
opennet-server --host 0.0.0.0 --port 8765
```

```python
import asyncio
from opennet import OpenNetClient

async def main():
    async with OpenNetClient("127.0.0.1") as client:
        await client.send("demo/message", {"hello": "OpenNet"})

asyncio.run(main())
```

The complete documentation, ESP32 Arduino library, examples, protocol
specification, and security guidance are in the
[OpenNet repository](https://github.com/devkyato/OpenNet).
