"""Immutable raw payload snapshots for replay and point-in-time auditing."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def save(source: str, payload, metadata: dict) -> str:
    received=metadata.get('received_at') or datetime.now(timezone.utc).isoformat()
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    day=received[:10]
    path=ROOT/'data'/'raw'/source/day/f'{digest}.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps({'metadata':metadata,'payload':payload},ensure_ascii=False,indent=2),encoding='utf-8')
    return str(path)
