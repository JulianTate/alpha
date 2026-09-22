"""Offline deterministic E2E proof of event -> graph -> signal -> manual trade -> outcome."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import alpha

def main():
    alpha.init(); event=alpha.ingest_event('ACME','production_change','ACME raises production guidance',source='demo')
    alpha.add_relationship('ACME','SUPPLY','customer','positive',.9,'Demo source says SUPPLY is a key customer supplier',exposure=.8)
    candidates=alpha.propagate(event); assert candidates and candidates[0]['ticker']=='SUPPLY'
    signal=alpha.make_signal(event,candidates[0],price=42.37); assert signal
    sid=alpha.buy(signal,'SUPPLY',20,42.37,'2026-09-14T08:00:00+00:00'); result=alpha.sell(sid,46.02,'2026-09-18T15:00:00+00:00')
    assert abs(result['gross_pnl'] - ((46.02-42.37)*20)) < 1e-9; assert result['return_pct']>8
    print({'event_id':event,'candidate':candidates[0],'signal_id':sid,'outcome':result,'report':alpha.report()})
if __name__=='__main__': main()
