"""Reply to each OpenNet DATA frame."""

import asyncio

from opennet import Frame, OpenNetServer, Peer


async def echo(peer: Peer, frame: Frame) -> None:
    print(peer.address, frame.topic, len(frame.payload))
    await peer.send_frame(
        Frame(
            frame.kind,
            frame.value_type,
            f"echo/{frame.topic}",
            frame.payload,
            frame.message_id,
        )
    )


async def main() -> None:
    await OpenNetServer(echo, host="0.0.0.0").serve_forever()


asyncio.run(main())
