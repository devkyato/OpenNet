# Authorizing topics

TLS answers one question: “Which certificate reached this connection?” The
application still has to answer another one: “What may that identity do?”

I thought about putting permissions into ONP/1 itself, but that would make the
wire protocol choose an identity model for every project. OpenNet v0.2.0 keeps
the frame format unchanged and gives the Python server an optional `authorizer`
instead. That keeps a small home sensor setup simple while still giving a
mutual-TLS deployment one clear place to enforce its rules.

## How the decision works

For every DATA frame, the server follows this order:

1. Parse and validate the ONP/1 frame.
2. Call the synchronous or asynchronous authorizer, when configured.
3. Stop on denial before duplicate handling, application code, or ACK.
4. Suppress an already-seen authorized message ID.
5. Run the application handler for a new authorized message.
6. Send an ACK when the frame requested one.

Oh! The order on step 3 matters. Authorization runs even when a message ID looks
like a duplicate, so a peer cannot reuse an accepted ID to sneak a different
topic past the policy.

A denial, or an exception raised by the authorizer, fails closed. The server
sends a generic `message not authorized` ERROR, increments
`ServerStats.authorization_denials`, and closes that connection. It does not
send private policy details to the peer.

## Mutual-TLS example

The example below allows one certificate common name to publish device status
and nothing else:

```python
from __future__ import annotations

import asyncio
import ssl

from opennet import Frame, OpenNetServer, Peer


def common_name(peer: Peer) -> str | None:
    certificate = peer.tls_peer_certificate
    if certificate is None:
        return None
    subject = {
        key: value
        for relative_name in certificate.get("subject", ())
        for key, value in relative_name
    }
    return subject.get("commonName")


def authorize(peer: Peer, frame: Frame) -> bool:
    return (
        peer.tls_enabled
        and common_name(peer) == "greenhouse-01"
        and frame.topic.startswith("greenhouse/status/")
    )


async def handle(_peer: Peer, frame: Frame) -> None:
    print(frame.topic, frame.payload)


async def main() -> None:
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain("server.crt", "server.key")
    tls.load_verify_locations("devices-ca.crt")
    tls.verify_mode = ssl.CERT_REQUIRED

    server = OpenNetServer(
        handle,
        host="0.0.0.0",
        ssl_context=tls,
        authorizer=authorize,
    )
    await server.serve_forever()


asyncio.run(main())
```

`tls_peer_certificate` is the dictionary returned by Python’s TLS layer after
the configured certificate checks. It is `None` on plaintext connections and
when no peer certificate is available. A production policy can match a subject,
issuer, serial number, or another certificate field, but it should use a stable
identity your own certificate process controls.

## Boundaries

- The authorizer is a Python server API; it adds no ONP/1 bytes or negotiation.
- Certificate identity depends on a correctly configured `SSLContext`.
- Topic authorization does not validate payload contents.
- Common names are convenient for the example, not a universal identity scheme.
- Revocation, certificate rotation, audit storage, and durable operation IDs
  remain deployment responsibilities.

See the [security guide](security.md) for the broader threat model and the
[protocol specification](protocol.md) for the unchanged ONP/1 frame rules.
