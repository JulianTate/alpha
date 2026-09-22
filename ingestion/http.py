"""Small dependency-free HTTP client with bounded retries and provenance metadata."""
from __future__ import annotations
import json, os, random, time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

USER_AGENT = os.getenv('ALPHA_SEC_USER_AGENT', 'JarvisAlpha/0.1 research contact-not-configured@example.invalid')


def get_bytes(url: str, *, headers=None, timeout=20, min_interval=0.2, retries=3, backoff=1.0):
    h={'User-Agent': USER_AGENT, 'Accept':'*/*'}
    if headers: h.update(headers)
    last_error=None
    for attempt in range(max(0, int(retries))+1):
        time.sleep(max(0.0, min_interval))
        req=Request(url, headers=h)
        try:
            with urlopen(req, timeout=timeout) as response:
                body=response.read()
                received=datetime.now(timezone.utc).isoformat()
                return body, {'url':url,'received_at':received,'http_status':getattr(response,'status',200),'content_length':len(body),'attempts':attempt+1}
        except HTTPError as exc:
            last_error=exc
            retryable=exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt >= int(retries): raise
            retry_after=exc.headers.get('Retry-After') if exc.headers else None
            try: delay=min(30.0,float(retry_after)) if retry_after else min(30.0,backoff*(2**attempt)+random.random()*0.25)
            except ValueError: delay=min(30.0,backoff*(2**attempt)+random.random()*0.25)
            time.sleep(delay)
    raise last_error


def get_json(url: str, *, headers=None, timeout=20, min_interval=0.2, retries=3, backoff=1.0):
    body, meta=get_bytes(url,headers=headers,timeout=timeout,min_interval=min_interval,retries=retries,backoff=backoff)
    return json.loads(body.decode('utf-8')), meta
