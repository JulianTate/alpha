"""Optional Telegram delivery. Credentials are read only from environment."""
import json, os, urllib.parse, urllib.request

def send(message: str) -> dict:
    token=os.getenv('ALPHA_TELEGRAM_BOT_TOKEN'); chat=os.getenv('ALPHA_TELEGRAM_CHAT_ID')
    if not token or not chat: return {'status':'not_configured','message':'Set ALPHA_TELEGRAM_BOT_TOKEN and ALPHA_TELEGRAM_CHAT_ID outside the repository.'}
    url=f'https://api.telegram.org/bot{token}/sendMessage'
    data=urllib.parse.urlencode({'chat_id':chat,'text':message}).encode()
    with urllib.request.urlopen(urllib.request.Request(url,data=data),timeout=15) as r: return json.load(r)
