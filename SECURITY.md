# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability in seqpack, please **do not** open a
public GitHub issue. Instead, report it privately using GitHub's
[private vulnerability reporting](https://github.com/CapitalOne-Research/sequence-compression/security/advisories/new)
feature for this repository.

Please include:

- A description of the vulnerability and its potential impact.
- Steps to reproduce (input values, pipeline string, and/or a minimal script).
- The affected version(s) of seqpack.

We aim to acknowledge new reports within 5 business days.

## Scope

seqpack is a data serialization/compression library. Reports of particular
interest include:

- Deserialization (`decode_*`) behavior that can be driven to excessive
  memory/CPU usage or crashes by attacker-controlled wire-format input.
- Any code path that could lead to arbitrary code execution.

Reports about the `web/` demo playground (a local development tool, not
intended for production or public deployment) are welcome but lower priority.

## Supported versions

Security fixes are made against the latest released version on PyPI. There
is no long-term support for older releases at this time.
