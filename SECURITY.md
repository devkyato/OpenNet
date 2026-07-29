# Security Policy

## Supported versions

Security fixes are provided for the latest released minor version. OpenNet is
currently pre-1.0 and should not be used as the only safety mechanism in critical
systems.

## Reporting a vulnerability

Use **Security > Report a vulnerability** in this GitHub repository. Do not open a
public issue containing exploit details, credentials, private addresses, or device
identifiers. Include affected versions, reproduction steps, impact, and a proposed
fix if available.

The maintainer aims to acknowledge a complete report within seven days and will
coordinate disclosure after a fix is available.

## Threat model

- ONP/1 CRC-32 detects transmission errors, not malicious modification.
- Plain TCP provides no confidentiality, peer identity, or replay protection.
- Use TLS with certificate validation across untrusted networks.
- Do not use `setInsecure()` in production.
- Applications must authorize topics and validate payloads. Python servers can
  use the optional pre-handler `authorizer`; other deployments must enforce an
  equivalent application policy.
- The 16 MiB frame limit reduces memory-exhaustion risk; deployments should choose
  a smaller application limit appropriate for their hardware.

The CLI defaults to loopback and requires an explicit flag for remote plaintext.
Mutual TLS is available when deployments must authenticate client devices. See the
[security guide](docs/security.md) for commands, limits, and deployment checklists.
