# Security

## Reporting a Vulnerability

Please report security vulnerabilities by opening a private GitHub issue or
contacting the maintainer directly. Do not open public issues for security bugs.

## Environment Variables

All secrets (API keys, webhooks, tokens) must be provided via environment
variables. Never commit `.env` files containing real credentials.

## Credential Rotation

If you believe credentials from this repository have been compromised,
rotate them immediately in the respective service dashboards.
