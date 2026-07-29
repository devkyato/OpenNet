# Contributing to OpenNet

Thank you for helping. Contributions from students and first-time open-source
developers are especially welcome.

## Choose a task

Comment on an existing issue before starting substantial work. Issues labeled
`good first issue` are scoped for newcomers; `help wanted` items may require
protocol or embedded experience. For a new idea, open an issue and explain the
problem before proposing an API.

## Development setup

Python:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e "./python[dev]"
.venv/Scripts/python -m pytest
```

On Linux/macOS, activate with `source .venv/bin/activate`. For embedded work,
install PlatformIO and run:

```bash
pio test -e native
pio run -e esp32dev
```

## Pull requests

1. Branch from `main`.
2. Make one coherent change with tests and documentation.
3. Use a Conventional Commit subject such as `feat: add discovery packet`.
4. Run the relevant checks locally.
5. Complete the pull-request checklist and link the issue.

Do not add generated build output or credentials. Protocol changes must update
`docs/protocol.md` and include cross-language test vectors. Compatibility claims
must name the exact board/OS, dependency versions, and test procedure.

## Review

Maintainers review correctness, compatibility, tests, security, and clarity.
Authors cannot approve their own pull requests; another reviewer should approve
before merge when one is available. CI must pass.
