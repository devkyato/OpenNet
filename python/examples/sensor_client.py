"""Send sample telemetry to an OpenNet server."""

import argparse
import asyncio
import random

from opennet import OpenNetClient


async def run(host: str, port: int) -> None:
    async with OpenNetClient(host, port) as client:
        while True:
            await client.send(
                "lab/telemetry",
                {
                    "temperature_c": round(random.uniform(22, 28), 2),
                    "source": "python-example",
                },
            )
            await asyncio.sleep(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("host")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    asyncio.run(run(args.host, args.port))
