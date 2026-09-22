"""Point-in-time and provenance checks shared by ingestion adapters."""
from __future__ import annotations
from datetime import datetime

def parse_timestamp(value: str) -> datetime:
    if not value or 'T' not in value:
        raise ValueError('timestamp must be an ISO-8601 datetime with availability time')
    return datetime.fromisoformat(value.replace('Z','+00:00'))

def validate_observation(*, event_time: str, published_at: str, available_at: str, reaction_at: str | None = None) -> dict:
    event=parse_timestamp(event_time); published=parse_timestamp(published_at); available=parse_timestamp(available_at)
    if published < event: raise ValueError('publication time precedes event time')
    if available < published: raise ValueError('availability time precedes publication time')
    if reaction_at is not None and parse_timestamp(reaction_at) < available: raise ValueError('reaction time precedes availability time')
    return {'event_time':event.isoformat(),'published_at':published.isoformat(),'available_at':available.isoformat(),'reaction_at':reaction_at}

def usable_as_of(available_at: str, as_of: str) -> bool:
    return parse_timestamp(available_at) <= parse_timestamp(as_of)
