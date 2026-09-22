"""Jarvis Alpha: dependency-light event research, paper-trading and evaluation engine."""
from __future__ import annotations
import argparse, csv, hashlib, json, logging, math, os, re, sqlite3, statistics, sys, time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable

from ingestion.data_engine import ensure_data_tables, validate_rows, verify_stored_prices, freeze_dataset, record_dataset
from ingestion.coverage import assess_coverage
from ingestion.capability_gates import assess_capabilities
from ingestion.provenance import (ensure_provenance_tables, list_reconciliation_reports,
                                  list_retrieval_completeness, reconcile_update_run, record_membership,
                                  record_retrieval, record_retrieval_completeness, record_reconciliation_report,
                                  record_update_summary)
from ingestion.session_completeness import assess_session_completeness
from ingestion.tiingo import CAPABILITY as TIINGO_CAPABILITY
from research.registry import ensure_registry_tables, freeze_dataset_record, register_strategy_genome, list_strategy_genomes
from research.paper import ensure_paper_tables, paper_report
from research.lab_runner import ensure_lab_tables, run_research_campaign
from research.playbooks import ensure_playbook_tables, register_builtin_playbooks, list_playbooks
from ingestion.openbb import availability as openbb_availability
from research.council import ensure_council_tables, run_council
from ingestion.data_manager import ensure_manager_tables, plan_update
from ingestion.dataset_contract import ensure_dataset_contract_tables, register_dataset_contract
from research.evidence_library import ensure_evidence_tables, register_builtin_evidence, list_evidence
from research.predictions import ensure_prediction_tables, list_model_versions
from research.scorecards import ensure_scorecard_tables, build_scorecard, get_scorecard, list_scorecards
from research.baseline_scorecards import build_baseline_suite
from research.holding_periods import compare_holding_periods
from research.shadow_validation import ensure_shadow_tables
from research.research_manager import ensure_manager_tables as ensure_research_manager_tables
from research.paper_outcomes import ensure_paper_outcome_tables
from research.paper_review import ensure_paper_review_tables, record_operator_review, evaluate_paper_observation_gate
from research.outcome_reconciliation import ensure_outcome_reconciliation_tables, reconcile_paper_outcomes
from research.shadow_validation import compare_champion_challenger
from research.manager_report import recovery_report
from research.validation_summary import ensure_validation_summary_tables
from research.promotion_gates import evaluate_promotion_gate
from ingestion.integrity import assess_integrity_controls
from research.core_intelligence import ensure_core_intelligence_tables, record_core_intelligence, list_core_intelligence
from research.core_outcomes import ensure_core_outcome_tables, record_core_outcome, compare_core_outcomes
from research.interpretation import ensure_interpretation_tables
from research.research_memory import ensure_research_memory_tables

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("ALPHA_DB", ROOT / "database" / "alpha.sqlite3"))
OBS = Path(os.getenv("ALPHA_OBSIDIAN", r"C:\Jarvis\Memory"))
LOG = ROOT / "logs" / "alpha.log"
LOG.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=LOG, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY, ticker TEXT UNIQUE NOT NULL, name TEXT, sector TEXT, market_cap REAL, active INTEGER DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS securities(id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL REFERENCES companies(id), ticker TEXT NOT NULL, currency TEXT DEFAULT 'USD', exchange TEXT, UNIQUE(company_id,ticker));
CREATE TABLE IF NOT EXISTS source_documents(id INTEGER PRIMARY KEY, source TEXT NOT NULL, url TEXT, published_at TEXT, received_at TEXT NOT NULL, content_hash TEXT UNIQUE, title TEXT, raw_text TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, event_key TEXT UNIQUE NOT NULL, company_id INTEGER REFERENCES companies(id), event_type TEXT NOT NULL, headline TEXT NOT NULL, source_document_id INTEGER REFERENCES source_documents(id), published_at TEXT NOT NULL, available_at TEXT, market_timestamp TEXT, effective_date TEXT, direction TEXT, strength REAL DEFAULT 0, facts_json TEXT DEFAULT '{}', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS relationships(id INTEGER PRIMARY KEY, source_company_id INTEGER NOT NULL REFERENCES companies(id), destination_company_id INTEGER NOT NULL REFERENCES companies(id), relationship_type TEXT NOT NULL, direction TEXT NOT NULL, confidence REAL NOT NULL, evidence_class TEXT NOT NULL, evidence TEXT NOT NULL, source_document_id INTEGER REFERENCES source_documents(id), valid_from TEXT, valid_to TEXT, exposure REAL, created_at TEXT NOT NULL, UNIQUE(source_company_id,destination_company_id,relationship_type));
CREATE TABLE IF NOT EXISTS prices(id INTEGER PRIMARY KEY, security_id INTEGER NOT NULL REFERENCES securities(id), market_timestamp TEXT NOT NULL, open REAL, high REAL, low REAL, close REAL NOT NULL, volume REAL, source TEXT NOT NULL, UNIQUE(security_id,market_timestamp));
CREATE TABLE IF NOT EXISTS signals(id INTEGER PRIMARY KEY, signal_id TEXT UNIQUE NOT NULL, event_id INTEGER REFERENCES events(id), company_id INTEGER REFERENCES companies(id), strategy TEXT NOT NULL, direction TEXT NOT NULL, score REAL NOT NULL, expected_horizon TEXT NOT NULL, entry_low REAL, entry_high REAL, invalidation TEXT, thesis TEXT, bear_case TEXT, evidence_json TEXT DEFAULT '{}', strategy_version TEXT NOT NULL, status TEXT DEFAULT 'HYPOTHETICAL', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS manual_trades(id INTEGER PRIMARY KEY, signal_id INTEGER REFERENCES signals(id), ticker TEXT NOT NULL, direction TEXT NOT NULL, quantity REAL NOT NULL, entry_price REAL, entry_timestamp TEXT, exit_price REAL, exit_timestamp TEXT, currency TEXT DEFAULT 'USD', status TEXT NOT NULL, notes TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outcomes(id INTEGER PRIMARY KEY, signal_id INTEGER UNIQUE REFERENCES signals(id), status TEXT NOT NULL, exit_price REAL, exit_timestamp TEXT, gross_pnl REAL, return_pct REAL, holding_days REAL, benchmark_return REAL, sector_return REAL, mfe REAL, mae REAL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS missed_signals(id INTEGER PRIMARY KEY, signal_id INTEGER UNIQUE REFERENCES signals(id), marked_at TEXT NOT NULL, hypothetical_exit_price REAL, hypothetical_return_pct REAL, status TEXT DEFAULT 'TRACKING', notes TEXT);
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, signal_id INTEGER REFERENCES signals(id), alert_type TEXT NOT NULL, message TEXT NOT NULL, sent_at TEXT, delivery_status TEXT DEFAULT 'PENDING');
CREATE TABLE IF NOT EXISTS model_runs(id INTEGER PRIMARY KEY, purpose TEXT, model TEXT, prompt_version TEXT, input_hash TEXT, output_json TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS strategy_versions(version TEXT PRIMARY KEY, parameters_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS data_quality(id INTEGER PRIMARY KEY, source TEXT, check_name TEXT, status TEXT, details TEXT, checked_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_events_time ON events(published_at); CREATE INDEX IF NOT EXISTS ix_prices_security_time ON prices(security_id,market_timestamp); CREATE INDEX IF NOT EXISTS ix_signals_score ON signals(score DESC); CREATE INDEX IF NOT EXISTS ix_trades_status ON manual_trades(status);
'''

def now(): return datetime.now(timezone.utc).isoformat()
class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()
        return False

def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True); c=sqlite3.connect(DB_PATH, factory=ClosingConnection); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c

def init():
    with conn() as c:
        c.executescript(SCHEMA)
        ensure_data_tables(c)
        ensure_registry_tables(c)
        ensure_paper_tables(c)
        ensure_lab_tables(c)
        ensure_playbook_tables(c)
        register_builtin_playbooks(c)
        ensure_council_tables(c)
        ensure_manager_tables(c)
        ensure_dataset_contract_tables(c)
        ensure_evidence_tables(c)
        register_builtin_evidence(c)
        ensure_prediction_tables(c)
        ensure_scorecard_tables(c)
        ensure_shadow_tables(c)
        ensure_research_manager_tables(c)
        ensure_paper_outcome_tables(c)
        ensure_paper_review_tables(c)
        ensure_outcome_reconciliation_tables(c)
        ensure_validation_summary_tables(c)
        ensure_core_intelligence_tables(c)
        ensure_core_outcome_tables(c)
        ensure_interpretation_tables(c)
        ensure_research_memory_tables(c)
        ensure_provenance_tables(c)
        # Forward-compatible migration for databases created by the first slice.
        columns={r['name'] for r in c.execute('PRAGMA table_info(events)')}
        if 'available_at' not in columns: c.execute('ALTER TABLE events ADD COLUMN available_at TEXT')
        c.execute("INSERT OR IGNORE INTO strategy_versions VALUES(?,?,?)",('spillover-v1',json.dumps({'weights':{'event_strength':.2,'relationship':.2,'gap':.25,'history':.2,'liquidity':.1,'uncertainty':-.05}}),now()))

def add_company(ticker,name=None,sector=None):
    init(); ticker=ticker.upper()
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO companies(ticker,name,sector,created_at) VALUES(?,?,?,?)",(ticker,name or ticker,sector,now())); row=c.execute('SELECT * FROM companies WHERE ticker=?',(ticker,)).fetchone(); c.execute("INSERT OR IGNORE INTO securities(company_id,ticker) VALUES(?,?)",(row['id'],ticker)); return row['id']

def add_relationship(source,destination,kind,direction,confidence,evidence,evidence_class='FACT',exposure=0.0):
    a=add_company(source); b=add_company(destination); init()
    with conn() as c: c.execute("INSERT OR REPLACE INTO relationships(source_company_id,destination_company_id,relationship_type,direction,confidence,evidence_class,evidence,exposure,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(a,b,kind,direction,float(confidence),evidence_class,evidence,float(exposure),now()))

def ingest_event(ticker,event_type,headline,published_at=None,source='manual',url=None,direction='positive',strength=.7,available_at=None):
    init(); cid=add_company(ticker); published_at=published_at or now(); available_at=available_at or now(); key=hashlib.sha256(f'{source}|{url or headline}|{published_at}'.encode()).hexdigest()
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO source_documents(source,url,published_at,received_at,content_hash,title,raw_text) VALUES(?,?,?,?,?,?,?)",(source,url,published_at,now(),hashlib.sha256(headline.encode()).hexdigest(),headline,headline)); doc=c.execute('SELECT id FROM source_documents WHERE content_hash=?',(hashlib.sha256(headline.encode()).hexdigest(),)).fetchone()
        c.execute("INSERT OR IGNORE INTO events(event_key,company_id,event_type,headline,source_document_id,published_at,available_at,market_timestamp,direction,strength,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(key,cid,event_type,headline,doc['id'],published_at,available_at,published_at,direction,float(strength),now())); return c.execute('SELECT id FROM events WHERE event_key=?',(key,)).fetchone()['id']

def add_price(ticker, timestamp, close, volume=0, open_=None, high=None, low=None, source='manual'):
    cid=add_company(ticker); init()
    with conn() as c:
        sid=c.execute('SELECT id FROM securities WHERE company_id=?',(cid,)).fetchone()['id']; c.execute("INSERT OR REPLACE INTO prices(security_id,market_timestamp,open,high,low,close,volume,source) VALUES(?,?,?,?,?,?,?,?)",(sid,timestamp,open_,high,low,float(close),float(volume),source))

def percentile_gap(event_id, company_id):
    with conn() as c:
        e=c.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone(); rel=c.execute('SELECT * FROM relationships WHERE source_company_id=? OR destination_company_id=?',(e['company_id'],e['company_id'])).fetchall(); return rel

def propagate(event_id):
    init(); out=[]
    with conn() as c:
        e=c.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone();
        if not e: return []
        rels=c.execute('SELECT r.*,c.ticker FROM relationships r JOIN companies c ON c.id=CASE WHEN r.source_company_id=? THEN r.destination_company_id ELSE r.source_company_id END WHERE r.source_company_id=? OR r.destination_company_id=?',(e['company_id'],e['company_id'],e['company_id'])).fetchall()
        for r in rels:
            # Deterministic provisional estimate; all inputs are persisted for later calibration.
            impact=min(1.0, max(0.0, e['strength'] * r['confidence'] * max(.1, min(1.0, r['exposure'] or .5))))
            out.append({'ticker':r['ticker'],'relationship':r['relationship_type'],'direction':r['direction'],'confidence':r['confidence'],'impact':round(impact,4),'evidence_class':r['evidence_class'],'evidence':r['evidence']})
    return out

def score_candidate(event_id,candidate,price_reaction=0.0,historical_win_rate=.5,sample_count=0):
    # Versioned, bounded score. Sparse history is penalized rather than treated as proof.
    impact=candidate['impact']; rel=candidate['confidence']; gap=max(0,min(1,impact-abs(price_reaction))); hist=historical_win_rate*(min(1,sample_count/20))
    uncertainty=.35 if candidate['evidence_class']!='FACT' else .1
    score=100*(.2*impact+.2*rel+.25*gap+.2*hist+.1*(1-uncertainty)-.05*uncertainty)
    return round(max(0,min(100,score)),2)

def make_signal(event_id,candidate,price=0,price_reaction=0):
    score=score_candidate(event_id,candidate,price_reaction); ticker=candidate['ticker']; sid='ALP-'+hashlib.sha1(f'{event_id}|{ticker}|{now()}'.encode()).hexdigest()[:8].upper(); direction='BUY' if candidate['direction'] in ('positive','benefit') else 'SELL/WATCH'
    with conn() as c:
        cid=c.execute('SELECT id FROM companies WHERE ticker=?',(ticker,)).fetchone()['id']; thesis=f"{candidate['relationship']} relationship; estimated impact {candidate['impact']:.1%}; evidence suggests residual gap, not certainty."; c.execute("INSERT INTO signals(signal_id,event_id,company_id,strategy,direction,score,expected_horizon,entry_low,entry_high,invalidation,thesis,bear_case,evidence_json,strategy_version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(sid,event_id,cid,'Event Spillover',direction,score,'3-10 trading days',price*.98 if price else None,price*1.02 if price else None,'Economic mechanism contradicted or gap closes',thesis,'Relationship may be weak, already priced, or offset by counterevidence',json.dumps(candidate),'spillover-v1',now())); return c.execute('SELECT id FROM signals WHERE signal_id=?',(sid,)).fetchone()['id']

def buy(signal_id,ticker,qty,price,timestamp=None):
    with conn() as c:
        s=c.execute('SELECT * FROM signals WHERE signal_id=?',(signal_id,)).fetchone() or c.execute('SELECT * FROM signals WHERE id=?',(signal_id,)).fetchone();
        if not s: raise ValueError('signal not found')
        c.execute("INSERT INTO manual_trades(signal_id,ticker,direction,quantity,entry_price,entry_timestamp,status,created_at) VALUES(?,?,?,?,?,?,?,?)",(s['id'],ticker.upper(),'BUY',qty,price,timestamp or now(),'OPEN',now())); c.execute("UPDATE signals SET status='OPEN' WHERE id=?",(s['id'],)); return s['signal_id']

def sell(signal_id,price,timestamp=None):
    with conn() as c:
        # Accept the human-facing ALP-... ID or the internal integer ID.
        key=str(signal_id)
        s=c.execute('SELECT id FROM signals WHERE signal_id=? OR id=?',(key, int(key) if key.isdigit() else -1)).fetchone()
        if not s: raise ValueError('signal not found')
        t=c.execute("SELECT * FROM manual_trades WHERE signal_id=? AND status='OPEN' ORDER BY id DESC LIMIT 1",(s['id'],)).fetchone();
        if not t: raise ValueError('open trade not found')
        ts=timestamp or now(); pnl=(float(price)-t['entry_price'])*t['quantity']; ret=(float(price)/t['entry_price']-1)*100; c.execute("UPDATE manual_trades SET exit_price=?,exit_timestamp=?,status='CLOSED' WHERE id=?",(price,ts,t['id'])); c.execute("INSERT OR REPLACE INTO outcomes(signal_id,status,exit_price,exit_timestamp,gross_pnl,return_pct,holding_days,created_at) VALUES(?,?,?,?,?,?,?,?)",(t['signal_id'],'CLOSED',price,ts,pnl,ret,0,now())); c.execute("UPDATE signals SET status='CLOSED' WHERE id=?",(t['signal_id'],)); return {'signal_id':signal_id,'gross_pnl':pnl,'return_pct':ret}

def mark_missed(signal_id, exit_price=None, notes=''):
    init()
    with conn() as c:
        key=str(signal_id)
        s=c.execute('SELECT * FROM signals WHERE signal_id=? OR id=?',(key, int(key) if key.isdigit() else -1)).fetchone()
        if not s: raise ValueError('signal not found')
        hypothetical=(float(exit_price)/float(s['entry_low'])-1)*100 if exit_price is not None and s['entry_low'] else None
        c.execute("INSERT OR REPLACE INTO missed_signals(signal_id,marked_at,hypothetical_exit_price,hypothetical_return_pct,status,notes) VALUES(?,?,?,?,?,?)",(s['id'],now(),exit_price,hypothetical,'TRACKING',notes))
        c.execute("UPDATE signals SET status='MISSED' WHERE id=?",(s['id'],))
        return s['signal_id']

def data_update(symbols=None, market='us', start='2011-01-01', end=None):
    """Acquire Tiingo observations; never substitutes or fabricates rows."""
    from ingestion.data_engine import ProviderCapability, record_capability, validate_rows
    from ingestion.tiingo import CAPABILITY, get_history
    end=end or datetime.now(timezone.utc).date().isoformat()
    symbols=[s.upper() for s in (symbols or [])]
    if not symbols:
        with conn() as c: symbols=[r['ticker'] for r in c.execute('SELECT ticker FROM companies WHERE active=1 ORDER BY ticker')]
    init()
    with conn() as c: record_capability(c,CAPABILITY)
    results=[]
    for symbol in symbols:
        try:
            result=get_history(symbol,start,end)
            issues=validate_rows(result.get('rows',[]))
            invalid=[issue for issue in issues if issue.status=='INVALID']
            if invalid:
                result_row={'symbol':symbol,'status':'DATA_INVALID','count':len(result.get('rows',[])),'issues':[asdict(issue) for issue in invalid]}
                with conn() as evidence_connection:
                    record_retrieval(evidence_connection, provider='tiingo', symbol=symbol,
                                     requested_start=start, requested_end=end,
                                     retrieved_at=result.get('metadata', {}).get('received_at', now()),
                                     response_status='INVALID', row_count=result.get('count', 0),
                                     source_snapshot_hash=result.get('metadata', {}).get('snapshot_path'),
                                     metadata=result.get('metadata', {}))
                results.append(result_row)
                continue
            for row in result.get('rows',[]): add_price(symbol,row['market_timestamp'],row['close'],row.get('volume',0),row.get('open'),row.get('high'),row.get('low'),'tiingo')
            retrieval_metadata=result.get('metadata',{})
            with conn() as evidence_connection:
                record_retrieval(evidence_connection, provider='tiingo', symbol=symbol,
                                 requested_start=start, requested_end=end,
                                 retrieved_at=retrieval_metadata.get('received_at', now()),
                                 response_status='OK' if result.get('count') else 'EMPTY',
                                 row_count=result.get('count', 0),
                                 source_snapshot_hash=retrieval_metadata.get('snapshot_path'),
                                 metadata=retrieval_metadata)
            results.append({'symbol':symbol,'status':'DATA_READY' if result.get('count') else 'DATA_UNRESOLVED','count':result.get('count',0),'metadata':retrieval_metadata})
        except Exception as exc:
            result_row={'symbol':symbol,'status':'DATA_BLOCKED','count':0,'error_type':type(exc).__name__,'error':str(exc)[:240]}
            with conn() as evidence_connection:
                record_retrieval(evidence_connection, provider='tiingo', symbol=symbol,
                                 requested_start=start, requested_end=end,
                                 retrieved_at=now(), response_status='BLOCKED', row_count=0,
                                 metadata={'error_type': type(exc).__name__, 'error': str(exc)[:240]})
            results.append(result_row)
    status='DATA_READY' if results and all(r.get('status')=='DATA_READY' for r in results) else ('DATA_PARTIAL' if any(r.get('status')=='DATA_READY' for r in results) else 'DATA_BLOCKED')
    with conn() as evidence_connection:
        run_summary=record_update_summary(evidence_connection, provider='tiingo', requested_start=start,
                                          requested_end=end, universe=symbols, results=results, status=status)
        reconciliation_report = record_reconciliation_report(evidence_connection, run_summary['run_id'])
    return {'market':market,'provider':'tiingo','start':start,'end':end,'results':results,'status':status,
            'run_summary':run_summary, 'reconciliation_report':reconciliation_report}


def data_status():
    init()
    with conn() as c:
        companies=c.execute('SELECT COUNT(*) n FROM companies WHERE active=1').fetchone()['n']
        securities=c.execute('SELECT COUNT(*) n FROM securities').fetchone()['n']
        prices=c.execute('SELECT COUNT(*) n, MIN(market_timestamp) first_ts, MAX(market_timestamp) last_ts FROM prices').fetchone()
        datasets=c.execute('SELECT COUNT(*) n FROM datasets').fetchone()['n']
        return {'status':'OK' if prices['n'] else 'DATA_BLOCKED','active_companies':companies,'securities':securities,'price_rows':prices['n'],'coverage_start':prices['first_ts'],'coverage_end':prices['last_ts'],'frozen_datasets':datasets,'message':None if prices['n'] else 'No canonical market observations are available; research cannot proceed.'}


def data_verify():
    init()
    with conn() as c:
        return verify_stored_prices(c)


def data_freeze(expected_sessions=None):
    init()
    with conn() as c:
        quality=verify_stored_prices(c)
        if quality['status'] != 'VALID':
            return {'status':'DATA_BLOCKED','quality':quality,'message':'Dataset cannot be frozen until every stored security passes validation.'}
        rows=[dict(r) for r in c.execute('''SELECT s.ticker AS symbol,p.security_id,p.market_timestamp AS timestamp,p.open,p.high,p.low,p.close,p.volume FROM prices p JOIN securities s ON s.id=p.security_id ORDER BY p.security_id,p.market_timestamp''')]
        expected_symbols=sorted({row['ticker'] for row in c.execute('SELECT ticker FROM companies WHERE active=1 ORDER BY ticker')})
        if not rows:
            return {'status':'DATA_BLOCKED','quality':quality,'expected_symbols':expected_symbols,'message':'No canonical observations are available.'}
        observed_symbols=sorted({r['symbol'] for r in rows})
        coverage=assess_coverage(rows, symbols=expected_symbols,
                                 requested_start=rows[0]['timestamp'], requested_end=rows[-1]['timestamp'])
        missing_symbols=sorted(set(expected_symbols) - set(observed_symbols))
        session_reports={}
        if expected_sessions is not None:
            expected_sessions=[str(value) for value in expected_sessions]
            for symbol in expected_symbols:
                symbol_rows=[r['timestamp'] for r in rows if r['symbol'] == symbol]
                session_reports[symbol]=assess_session_completeness(observed=symbol_rows, expected=expected_sessions)
            incomplete_sessions={symbol: report for symbol, report in session_reports.items() if report['status'] != 'READY'}
            if incomplete_sessions:
                return {'status':'DATA_BLOCKED','quality':quality,'coverage':coverage,
                        'expected_symbols':expected_symbols,'observed_symbols':observed_symbols,
                        'missing_symbols':missing_symbols,'session_reports':session_reports,
                        'message':'Dataset cannot be frozen until every symbol passes the declared session calendar.'}
        if missing_symbols:
            return {'status':'DATA_BLOCKED','quality':quality,'coverage':coverage,
                    'expected_symbols':expected_symbols,'observed_symbols':observed_symbols,
                    'missing_symbols':missing_symbols,
                    'message':'Dataset cannot be frozen while active-universe symbols have no observations.'}
        if coverage['status'] != 'READY':
            return {'status':'DATA_BLOCKED','quality':quality,'coverage':coverage,
                    'message':'Dataset cannot be frozen until every symbol has explicit requested-range coverage.'}
        capabilities=assess_capabilities([TIINGO_CAPABILITY], provider_names=['tiingo'])
        if capabilities['status'] != 'READY':
            return {'status':'DATA_BLOCKED','quality':quality,'coverage':coverage,
                    'capabilities':capabilities,
                    'message':'Dataset cannot be frozen until provider capabilities are explicitly declared.'}
        metadata=freeze_dataset(['tiingo'],rows,start=rows[0]['timestamp'],end=rows[-1]['timestamp'],adjustment_policy='raw_close_and_adjusted_close_preserved')
        metadata['universe_definition']={'type':'pilot','symbols':sorted({r['symbol'] for r in rows})}
        record_dataset(c,metadata,'FROZEN')
        coverage_start_date=metadata['coverage_start'][:10]
        coverage_end_date=metadata['coverage_end'][:10]
        update_run=c.execute('''SELECT run_id FROM data_update_run_summaries
                               WHERE provider=? AND requested_start<=? AND requested_end>=?
                               ORDER BY created_at DESC LIMIT 1''',
                             ('tiingo', coverage_start_date, coverage_end_date)).fetchone()
        retrieval_report=record_retrieval_completeness(
            c, dataset_id=metadata['dataset_id'], provider='tiingo',
            requested_start=metadata['coverage_start'], requested_end=metadata['coverage_end'],
            expected_symbols=expected_symbols,
            update_run_id=update_run['run_id'] if update_run else None)
        for symbol in sorted({r['symbol'] for r in rows}):
            record_membership(c, dataset_id=metadata['dataset_id'], symbol=symbol,
                              valid_from=metadata['coverage_start'], valid_to=metadata['coverage_end'],
                              inclusion_basis='frozen observed universe', source_snapshot_hash=metadata['dataset_hash'])
        contract=register_dataset_contract(c, {
            'dataset_id': metadata['dataset_id'],
            'universe_definition': metadata['universe_definition']['symbols'],
            'as_of_policy': 'information_available_at_observation_timestamp',
            'corporate_action_policy': metadata['adjustment_policy'],
            'survivorship_policy': 'universe_definition_persisted_with_dataset',
            'source_snapshot_hash': metadata['dataset_hash'],
            'quality_status': quality['status'],
            'capability_report': capabilities,
            'coverage_report': coverage,
            'retrieval_completeness_report': retrieval_report,
        })
        return {'status':'DATA_READY','dataset':metadata,'contract':contract,'quality':quality,
                'retrieval_completeness_report': retrieval_report}


def report():
    init();
    with conn() as c:
        return {'signals':c.execute('SELECT COUNT(*) n FROM signals').fetchone()['n'],'open_trades':c.execute("SELECT COUNT(*) n FROM manual_trades WHERE status='OPEN'").fetchone()['n'],'closed_trades':c.execute("SELECT COUNT(*) n FROM manual_trades WHERE status='CLOSED'").fetchone()['n'],'missed_signals':c.execute('SELECT COUNT(*) n FROM missed_signals').fetchone()['n'],'by_status':[dict(r) for r in c.execute('SELECT status,COUNT(*) n FROM signals GROUP BY status')]}

def export_note(title,text):
    p=OBS/'03_RESEARCH'/'Alpha'; p.mkdir(parents=True,exist_ok=True); (p/(title+'.md')).write_text(text,encoding='utf-8'); return str(p/(title+'.md'))

def cli():
    ap=argparse.ArgumentParser(description='Jarvis Alpha deterministic research engine (paper/manual only).'); sub=ap.add_subparsers(dest='cmd'); sub.add_parser('init'); sub.add_parser('report'); sub.add_parser('paper-report'); sub.add_parser('playbooks'); sub.add_parser('evidence-library'); sub.add_parser('model-version-list'); sub.add_parser('scorecard-list').add_argument('--experiment'); sub.add_parser('scorecard').add_argument('--id',required=True); sb=sub.add_parser('build-scorecard'); sb.add_argument('--experiment',required=True); sb.add_argument('--dataset',required=True); sb.add_argument('--scope',default='OOS'); sb.add_argument('--minimum-observations',type=int,default=1); sb.add_argument('--min-as-of'); sb.add_argument('--max-as-of'); sb.add_argument('--model-version',action='append'); sub.add_parser('openbb-status'); cr=sub.add_parser('council-review'); cr.add_argument('ticker'); cr.add_argument('--as-of',required=True); dp=sub.add_parser('data-plan'); dp.add_argument('--symbol',action='append'); dp.add_argument('--start',required=True); dp.add_argument('--end',required=True); dp.add_argument('--provider',default='tiingo'); sub.add_parser('data-status'); sub.add_parser('data-verify'); sub.add_parser('data-freeze'); sub.add_parser('research-manager-report'); sub.add_parser('provider-health'); rcpt=sub.add_parser('retrieval-completeness'); rcpt.add_argument('--dataset',required=True); rcpt.add_argument('--provider',default='tiingo'); rcpt.add_argument('--symbol',action='append',required=True); rcpt.add_argument('--start',required=True); rcpt.add_argument('--end',required=True); sub.add_parser('retrieval-completeness-list').add_argument('--dataset'); rup=sub.add_parser('reconcile-update-run'); rup.add_argument('--run-id',required=True); rrp=sub.add_parser('reconciliation-report'); rrp.add_argument('--run-id',required=True); sub.add_parser('reconciliation-report-list').add_argument('--run-id'); du=sub.add_parser('data-update'); du.add_argument('--market',default='us'); du.add_argument('--symbol',action='append'); du.add_argument('--start',default='2011-01-01'); du.add_argument('--end');
    e=sub.add_parser('event'); e.add_argument('ticker'); e.add_argument('event_type'); e.add_argument('headline'); e.add_argument('--source',default='manual');
    r=sub.add_parser('relationship'); r.add_argument('source'); r.add_argument('destination'); r.add_argument('kind'); r.add_argument('--direction',default='positive'); r.add_argument('--confidence',type=float,default=.7); r.add_argument('--exposure',type=float,default=.5); r.add_argument('--evidence',default='User-supplied evidence');
    b=sub.add_parser('buy'); b.add_argument('signal'); b.add_argument('ticker'); b.add_argument('quantity',type=float); b.add_argument('price',type=float)
    s=sub.add_parser('sell'); s.add_argument('signal'); s.add_argument('price',type=float)
    sc=sub.add_parser('scan'); sc.add_argument('tickers', nargs='+'); sc.add_argument('--horizon', type=int, default=5)
    su=sub.add_parser('scan-universe'); su.add_argument('tickers', nargs='*'); su.add_argument('--horizon', type=int, default=5); su.add_argument('--limit', type=int, default=10); su.add_argument('--min-history', type=int, default=60)
    tv=sub.add_parser('import-tradingview'); tv.add_argument('ticker'); tv.add_argument('csv_path')
    td=sub.add_parser('import-tradingview-dir'); td.add_argument('directory'); td.add_argument('--pattern',default='*.csv')
    cb=sub.add_parser('campaign-baseline'); cb.add_argument('--dataset',required=True); cb.add_argument('--symbols',nargs='+',required=True); cb.add_argument('--train-start',required=True); cb.add_argument('--train-end',required=True); cb.add_argument('--validation-start',required=True); cb.add_argument('--validation-end',required=True); cb.add_argument('--test-start',required=True); cb.add_argument('--test-end',required=True)
    bs=sub.add_parser('baseline-suite'); bs.add_argument('--dataset',required=True); bs.add_argument('--input',required=True); bs.add_argument('--cost-bps',type=float,required=True); bs.add_argument('--minimum-observations',type=int,default=20); bs.add_argument('--random-seed',default='RANDOM-V1')
    hp=sub.add_parser('holding-period-compare'); hp.add_argument('--input',required=True); hp.add_argument('--horizons',required=True); hp.add_argument('--quantity',type=float,default=1.0); hp.add_argument('--cost-bps',type=float,default=11.0); hp.add_argument('--minimum-observations',type=int,default=20)
    pg=sub.add_parser('promotion-gate'); pg.add_argument('--input',required=True); pg.add_argument('--dataset-status',required=True); pg.add_argument('--evidence-status',default='COMPLETE')
    pr=sub.add_parser('paper-review'); pr.add_argument('--candidate-id',required=True); pr.add_argument('--decision',choices=['APPROVE_PAPER','REJECT','DEFER'],required=True); pr.add_argument('--reviewer',required=True); pr.add_argument('--rationale',required=True); pr.add_argument('--evidence',default='{}')
    pog=sub.add_parser('paper-observation-gate'); pog.add_argument('--candidate-id',required=True); pog.add_argument('--minimum-observations',type=int,default=1)
    orc=sub.add_parser('outcome-reconcile'); orc.add_argument('--candidate-id')
    sh=sub.add_parser('shadow-compare'); sh.add_argument('--champion-version',required=True); sh.add_argument('--challenger-version',required=True); sh.add_argument('--input',required=True)
    ic=sub.add_parser('integrity-assess'); ic.add_argument('--input',required=True)
    ci=sub.add_parser('core-intelligence-record'); ci.add_argument('--layer',choices=['ISA','CORE'],required=True); ci.add_argument('--subject',required=True); ci.add_argument('--as-of',required=True); ci.add_argument('--objective',default='GENERAL_RESEARCH'); ci.add_argument('--thesis',required=True); ci.add_argument('--context',default='{}'); ci.add_argument('--evidence',default='{}')
    cil=sub.add_parser('core-intelligence-list'); cil.add_argument('--layer',choices=['ISA','CORE'])
    co=sub.add_parser('core-outcome-record'); co.add_argument('--record-id',required=True); co.add_argument('--observed-at',required=True); co.add_argument('--outcome-type',required=True); co.add_argument('--value',type=float); co.add_argument('--source',default='manual'); co.add_argument('--notes',default=''); co.add_argument('--provenance',default='{}')
    coc=sub.add_parser('core-outcome-compare'); coc.add_argument('--record-id'); coc.add_argument('--observation-start'); coc.add_argument('--observation-end')
    sub.add_parser('strategy-genome-list')
    rc=sub.add_parser('research-campaign'); rc.add_argument('--dataset',required=True); rc.add_argument('--symbols',nargs='+',required=True); rc.add_argument('--family',choices=['MOMENTUM','TREND','BREAKOUT','MEAN_REVERSION','CROSS_SECTIONAL'],default='MOMENTUM'); rc.add_argument('--mode',choices=['FAST','STANDARD','DEEP'],default='STANDARD'); rc.add_argument('--budget',type=int,default=100); rc.add_argument('--train-start',required=True); rc.add_argument('--train-end',required=True); rc.add_argument('--validation-start',required=True); rc.add_argument('--validation-end',required=True); rc.add_argument('--oos-start',required=True); rc.add_argument('--oos-end',required=True); rc.add_argument('--report-dir',default=str(ROOT/'reports'))
    a=ap.parse_args();
    if a.cmd=='init': init(); print(DB_PATH)
    elif a.cmd=='playbooks':
        init()
        with conn() as c: print(json.dumps(list_playbooks(c), indent=2))
    elif a.cmd=='evidence-library':
        init()
        with conn() as c: print(json.dumps(list_evidence(c), indent=2))
    elif a.cmd=='model-version-list':
        init()
        with conn() as c: print(json.dumps(list_model_versions(c), indent=2))
    elif a.cmd=='strategy-genome-list':
        init()
        with conn() as c: print(json.dumps(list_strategy_genomes(c), indent=2))
    elif a.cmd=='scorecard-list':
        init()
        with conn() as c: print(json.dumps(list_scorecards(c, experiment_id=a.experiment), indent=2))
    elif a.cmd=='scorecard':
        init()
        with conn() as c: print(json.dumps(get_scorecard(c, a.id), indent=2))
    elif a.cmd=='build-scorecard':
        init()
        with conn() as c:
            print(json.dumps(build_scorecard(c, a.experiment, a.dataset, evaluation_scope=a.scope,
                minimum_observations=a.minimum_observations, min_as_of=a.min_as_of,
                max_as_of=a.max_as_of, model_versions=a.model_version), indent=2))
    elif a.cmd=='baseline-suite':
        rows = json.loads(Path(a.input).read_text(encoding='utf-8'))
        print(json.dumps(build_baseline_suite(rows, dataset_id=a.dataset, cost_bps=a.cost_bps,
            minimum_observations=a.minimum_observations, random_seed=a.random_seed), indent=2))
    elif a.cmd=='holding-period-compare':
        from research.backtest import CostModel
        rows = json.loads(Path(a.input).read_text(encoding='utf-8'))
        horizons = [int(value) for value in a.horizons.split(',') if value.strip()]
        cost = CostModel(fee_bps=a.cost_bps / 3, half_spread_bps=a.cost_bps / 3,
                         slippage_bps=a.cost_bps / 3)
        print(json.dumps(compare_holding_periods(rows, horizons, quantity=a.quantity,
            cost=cost, minimum_observations=a.minimum_observations), indent=2))
    elif a.cmd=='promotion-gate':
        payload = json.loads(Path(a.input).read_text(encoding='utf-8'))
        scorecard = payload.get('scorecard', payload)
        print(json.dumps(evaluate_promotion_gate(dataset_status=a.dataset_status,
            evidence_status=a.evidence_status, scorecard=scorecard), indent=2))
    elif a.cmd=='paper-review':
        init()
        with conn() as c:
            print(json.dumps(record_operator_review(c, a.candidate_id, decision=a.decision,
                reviewer=a.reviewer, rationale=a.rationale, evidence=json.loads(a.evidence)), indent=2))
    elif a.cmd=='paper-observation-gate':
        init()
        with conn() as c:
            print(json.dumps(evaluate_paper_observation_gate(c, a.candidate_id,
                minimum_observations=a.minimum_observations), indent=2))
    elif a.cmd=='outcome-reconcile':
        init()
        with conn() as c:
            print(json.dumps(reconcile_paper_outcomes(c, candidate_id=a.candidate_id), indent=2))
    elif a.cmd=='shadow-compare':
        init()
        rows = json.loads(Path(a.input).read_text(encoding='utf-8'))
        with conn() as c:
            print(json.dumps(compare_champion_challenger(c, champion_version=a.champion_version,
                challenger_version=a.challenger_version, observations=rows), indent=2))
    elif a.cmd=='integrity-assess':
        controls = json.loads(Path(a.input).read_text(encoding='utf-8'))
        print(json.dumps(assess_integrity_controls(controls), indent=2))
    elif a.cmd=='core-intelligence-record':
        init()
        with conn() as c:
            print(json.dumps(record_core_intelligence(c, layer=a.layer, subject=a.subject, as_of=a.as_of,
                objective=a.objective, thesis=a.thesis, context=json.loads(a.context),
                evidence=json.loads(a.evidence)), indent=2))
    elif a.cmd=='core-intelligence-list':
        init()
        with conn() as c:
            print(json.dumps(list_core_intelligence(c, layer=a.layer), indent=2))
    elif a.cmd=='core-outcome-record':
        init()
        with conn() as c:
            print(json.dumps(record_core_outcome(c, record_id=a.record_id, observed_at=a.observed_at,
                outcome_type=a.outcome_type, value=a.value, source=a.source, notes=a.notes,
                provenance=json.loads(a.provenance)), indent=2))
    elif a.cmd=='core-outcome-compare':
        init()
        with conn() as c:
            print(json.dumps(compare_core_outcomes(c, record_id=a.record_id,
                observation_start=a.observation_start, observation_end=a.observation_end), indent=2))
    elif a.cmd=='openbb-status': print(json.dumps(openbb_availability(), indent=2))
    elif a.cmd=='council-review':
        init()
        with conn() as c: print(json.dumps(run_council(c, ticker=a.ticker, as_of=a.as_of), indent=2))
    elif a.cmd=='data-status': print(json.dumps(data_status(),indent=2))
    elif a.cmd=='data-plan':
        init()
        with conn() as c: print(json.dumps(plan_update(c, symbols=a.symbol, start=a.start, end=a.end, provider=a.provider), indent=2))
    elif a.cmd=='provider-health':
        from ingestion.tiingo import health_check
        print(json.dumps(health_check(),indent=2))
    elif a.cmd=='data-update': print(json.dumps(data_update(a.symbol,a.market,a.start,a.end),indent=2))
    elif a.cmd=='data-verify': print(json.dumps(data_verify(),indent=2))
    elif a.cmd=='data-freeze': print(json.dumps(data_freeze(),indent=2))
    elif a.cmd=='retrieval-completeness':
        init()
        with conn() as c:
            print(json.dumps(record_retrieval_completeness(c, dataset_id=a.dataset, provider=a.provider,
                requested_start=a.start, requested_end=a.end, expected_symbols=a.symbol), indent=2))
    elif a.cmd=='retrieval-completeness-list':
        init()
        with conn() as c: print(json.dumps(list_retrieval_completeness(c, dataset_id=a.dataset), indent=2))
    elif a.cmd=='reconcile-update-run':
        init()
        with conn() as c:
            try:
                result = reconcile_update_run(c, a.run_id)
            except KeyError as exc:
                result = {'status':'NOT_FOUND', 'run_id':a.run_id, 'error':str(exc)}
            print(json.dumps(result, indent=2))
    elif a.cmd=='reconciliation-report':
        init()
        with conn() as c:
            try:
                result = record_reconciliation_report(c, a.run_id)
            except KeyError as exc:
                result = {'status':'NOT_FOUND', 'run_id':a.run_id, 'error':str(exc)}
            print(json.dumps(result, indent=2))
    elif a.cmd=='reconciliation-report-list':
        init()
        with conn() as c: print(json.dumps(list_reconciliation_reports(c, run_id=a.run_id), indent=2))
    elif a.cmd=='research-manager-report':
        init()
        with conn() as c: print(json.dumps(recovery_report(c), indent=2))
    elif a.cmd=='report': print(json.dumps(report(),default=lambda x:dict(x),indent=2))
    elif a.cmd=='paper-report':
        init()
        with conn() as c: print(json.dumps(paper_report(c),indent=2))
    elif a.cmd=='campaign-baseline':
        from research.campaign import run_baseline
        init()
        with conn() as c:
            result=run_baseline(c,a.dataset,a.symbols,{'train':(a.train_start,a.train_end),'validation':(a.validation_start,a.validation_end),'test':(a.test_start,a.test_end)})
        print(json.dumps(result,indent=2))
    elif a.cmd=='research-campaign':
        init()
        with conn() as c:
            result=run_research_campaign(c,dataset_id=a.dataset,universe=a.symbols,family=a.family,mode=a.mode,experiment_budget=a.budget,report_dir=a.report_dir,periods={'train':(a.train_start,a.train_end),'validation':(a.validation_start,a.validation_end),'oos':(a.oos_start,a.oos_end)})
        print(json.dumps(result,indent=2))
    elif a.cmd=='event': print(ingest_event(a.ticker,a.event_type,a.headline,source=a.source))
    elif a.cmd=='relationship': add_relationship(a.source,a.destination,a.kind,a.direction,a.confidence,a.evidence,exposure=a.exposure); print('relationship stored')
    elif a.cmd=='buy': print(buy(a.signal,a.ticker,a.quantity,a.price))
    elif a.cmd=='sell': print(json.dumps(sell(a.signal,a.price)))
    elif a.cmd in ('scan','scan-universe'):
        from research.strategy_scan import Bar, scan_bars, result_dict, rank_results
        init(); results=[]
        with conn() as c:
            tickers=[x.upper() for x in a.tickers]
            if a.cmd=='scan-universe' and not tickers:
                tickers=[r['ticker'] for r in c.execute('SELECT ticker FROM companies WHERE active=1 ORDER BY ticker').fetchall()]
            for ticker in tickers:
                rows=c.execute('''SELECT p.market_timestamp,p.close,p.high,p.low,p.volume FROM prices p JOIN securities s ON s.id=p.security_id JOIN companies co ON co.id=s.company_id WHERE co.ticker=? ORDER BY p.market_timestamp''',(ticker,)).fetchall()
                bars=[Bar(r['market_timestamp'],float(r['close']),r['high'],r['low'],r['volume'] or 0) for r in rows]
                if len(bars)>=getattr(a,'min_history',0): results.append(scan_bars(ticker,bars,horizon=a.horizon))
                elif a.cmd=='scan': results.append({'ticker':ticker,'confidence_band':'NO_DATA' if not bars else 'INSUFFICIENT_EVIDENCE','warnings':[f'only {len(bars)} historical bars; minimum is {getattr(a,"min_history",0)}']})
        if a.cmd=='scan-universe': results=[result_dict(r) for r in rank_results(results,a.limit)]
        else: results=[result_dict(r) if hasattr(r,'ticker') else r for r in results]
        print(json.dumps(results,indent=2))
    elif a.cmd=='import-tradingview':
        from ingestion.tradingview import import_csv
        print(json.dumps(import_csv(a.csv_path,a.ticker),indent=2))
    elif a.cmd=='import-tradingview-dir':
        from ingestion.tradingview import import_csv
        directory=Path(a.directory); results=[]
        for path in sorted(directory.glob(a.pattern)):
            ticker=path.stem.upper().split('.')[0]
            try: results.append(import_csv(path,ticker))
            except Exception as exc: results.append({'status':'error','file':str(path),'error':str(exc)})
        print(json.dumps(results,indent=2))
    else: ap.print_help()
if __name__=='__main__': cli()
