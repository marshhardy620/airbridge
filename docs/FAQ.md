# FAQ

## Does AirBridge need an account or cloud server?

No. AirBridge is designed for devices on the same local network. Discovery and transfer happen over your Wi-Fi or LAN.

## Which platforms are supported?

The repository includes Windows, Android, iOS, and macOS code paths. Windows is the primary packaged release path today, while the mobile and macOS projects are source-first ports for testing and development.

## Why do devices sometimes fail to discover each other?

Local discovery depends on the network allowing UDP broadcast traffic and direct connections between devices. Guest Wi-Fi, school networks, corporate networks, VPNs, and firewall rules may block discovery even when both devices are online.

## Does AirBridge upload my files anywhere?

No. AirBridge is intended for direct local-network transfer. The project does not require a cloud relay for normal operation.

## Is this a replacement for encrypted file sharing?

Not yet. Treat AirBridge as a trusted-local-network tool. Do not use it for sensitive files on an untrusted network unless the protocol and platform security model meet your needs.

## What should I include in a bug report?

Include the operating systems, AirBridge version or commit, whether both devices are on the same network, firewall or VPN status, the action you tried, and any console logs or screenshots that do not expose private data.
