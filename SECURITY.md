# Security

- No broker integration or trade execution exists.
- No secrets are stored in SQLite, Git, Obsidian, Markdown, or logs.
- Telegram credentials, when configured, must be supplied through protected environment/secret storage and sent only to `api.telegram.org`.
- OpenClaw remains loopback-bound; no gateway exposure changes were made.
- Windows startup/service registration was not changed automatically because it is a persistent configuration change requiring explicit operator approval.
