# Jarvis Alpha

A local, manual-trading-only research and paper-tracking engine. It never connects to a broker and never places orders. The first version is deliberately dependency-light and records provenance, point-in-time timestamps, relationship evidence classes, versioned scoring, manual entries/exits, and outcomes in SQLite.

## Quick start

```powershell
cd C:\Jarvis\Alpha
python alpha.py init
python scripts\demo_e2e.py
python alpha.py report
```

Manual confirmation examples:

```powershell
python alpha.py buy ALP-XXXXXXXX SUPPLY 20 42.37
python alpha.py sell ALP-XXXXXXXX 46.02
```

The conversational Jarvis can use `integrations\jarvis_alpha.py` for read-only signal/open-trade queries. Research adapters live under `ingestion\`; event reactions and cost-aware validation primitives live under `research\`. Telegram is optional and disabled until environment variables are configured outside this directory. See `OPERATIONS.md` and `VALIDATION.md`.
