# Security Policy

## Scope

AirBridge transfers messages and files over a trusted local network. Security-sensitive reports may include issues around file receiving, path handling, local-network exposure, update behavior, or cross-platform protocol handling.

## Reporting a Vulnerability

Please do not open a public issue for vulnerabilities that could expose files, overwrite data, bypass local-network assumptions, or weaken update safety.

Report privately through GitHub's security reporting flow if available, or contact the maintainer through the GitHub profile.

Include:

- A short description of the issue.
- Sender and receiver platforms.
- Network setup.
- Steps to reproduce.
- Whether manual peer entry or automatic discovery was used.
- The affected endpoint, release asset, or app version if known.

## Local Network Assumption

AirBridge is designed for trusted Wi-Fi or LAN environments. It does not require accounts or cloud servers, but it also should not be treated as a hardened public-network file server. Do not accept files from unknown devices on untrusted public networks.

## Supported Versions

Security fixes target the latest code on `main` and the latest published release when applicable.