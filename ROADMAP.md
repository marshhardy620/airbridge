# Roadmap

This roadmap describes the direction of AirBridge. It is not a promise of dates; it is a public guide for what would make the project more useful and easier to trust.

## Current Focus

- Keep the shared UDP/HTTP protocol compatible across Windows, Android, iOS, and macOS.
- Improve discovery reliability on school, dorm, office, and segmented LANs.
- Keep the Windows release flow simple enough for non-developers to download and run.
- Make the repository easier for contributors to understand through protocol docs, issue forms, and platform notes.

## Near-Term Improvements

- Add screenshots or a short demo GIF to the README.
- Add a release checklist for Windows builds and source packages.
- Add lightweight protocol tests for `/api/state`, message sending, and file upload.
- Improve troubleshooting docs for firewall and manual-peer workflows.
- Document supported file-size limits per platform.

## Longer-Term Ideas

- Better transfer progress feedback.
- Optional pairing or device trust prompts.
- More robust duplicate-file handling.
- Better Android received-file browsing.
- Signed or checksum-verified release assets.

## Non-Goals

- Cloud relay servers.
- Account login.
- Public internet file sharing.
- Replacing platform-native secure sharing tools for untrusted networks.
