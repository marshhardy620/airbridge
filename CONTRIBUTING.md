# Contributing to AirBridge

Thanks for helping improve AirBridge. The project is a local-network file and message transfer tool, so the most important rule is to preserve protocol compatibility across platforms.

## Good First Contributions

- Improve setup instructions for Windows, Android, iOS, or macOS.
- Add clearer troubleshooting notes for firewall, Wi-Fi, and broadcast discovery issues.
- Improve UI text, error messages, or received-file handling.
- Add tests or scripts that validate the shared UDP/HTTP protocol.
- Document behavior on school, office, or router-segmented networks.
- Improve packaging notes for release assets.

## Compatibility Rules

AirBridge devices should continue to interoperate through the shared local-network protocol:

- UDP discovery on port `45678`.
- HTTP transfer endpoints such as `/api/state`, `/api/inbox/message`, and `/api/inbox/file`.
- Manual peer entry for networks where broadcast discovery is blocked.

If a change modifies the protocol, document the migration impact and update `docs/PROTOCOL.md` in the same PR.

## Before Opening a Pull Request

1. Keep changes focused and explain which platform is affected.
2. Test at least one send/receive flow when touching transfer logic.
3. Mention whether the change was tested on Windows, Android, iOS, or macOS.
4. Do not add cloud services, accounts, or external servers as required dependencies.
5. Keep received-file behavior predictable and avoid overwriting user files silently.

## Reporting Issues

When reporting a bug, include:

- Operating system and app version.
- Whether both devices are on the same Wi-Fi or local network.
- Whether automatic discovery or manual peer entry was used.
- Firewall prompts or network restrictions you noticed.
- The sender and receiver platforms.
- A short description of what was sent and what happened.

## Security Notes

AirBridge is intended for trusted local networks. Contributions should keep that assumption visible and should not weaken the warning around public or untrusted Wi-Fi.