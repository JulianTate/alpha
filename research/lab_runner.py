"""SQLite-backed bounded research-campaign runner."""
from __future__ import annotations
import json, subprocess, uuid
from pathlib import Path
from datetime import datetime, timezone
import sqlite3
from .laboratory import (StrategyDefinition, baseline_metrics, generate_hypotheses,
    multiple_testing, parameter_grid, research_gate, robustness, score_candidate,
    temporal_splits, html_report, walk_forward_folds)
from .registry import create_campaign, create_experiment, transition_campaign, now


def ensure_lab_tables(connection: sqlite3.Connection) -> None:
    connection.executescript("""
    CREATE TABLE IF NOT EXISTS strategy_definitions(
      strategy_fingerprint TEXT PRIMARY KEY, strategy_id TEXT NOT NULL,
      strategy_version TEXT NOT NULL, definition_json TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS laboratory_trials(
      trial_id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, experiment_id TEXT,
      hypothesis_id TEXT NOT NULL, strategy_fingerprint TEXT, split TEXT NOT NULL,
      parameters_json TEXT NOT NULL, metrics_json TEXT NOT NULL, status TEXT NOT NULL,
      created_at TEXT NOT NULL, UNIQUE(campaign_id,hypothesis_id,split,parameters_json));
    CREATE TABLE IF NOT EXISTS laboratory_reports(
      campaign_id TEXT PRIMARY KEY, report_json TEXT NOT NULL, markdown TEXT NOT NULL,
      html TEXT NOT NULL, created_at TEXT NOT NULL);
    """)


def _bars(connection, ticker: str):
    rows=connection.execute("""SELECT p.market_timestamp,p.open,p.high,p.low,p.close,p.volume
      FROM prices p JOIN securities s ON s.id=p.security_id JOIN companies c ON c.id=s.company_id
      WHERE c.ticker=? ORDER BY p.market_timestamp""",(ticker,)).fetchall()
    return [dict(timestamp=r[0],open=r[1],high=r[2],low=r[3],close=r[4],volume=r[5]) for r in rows]


def _code_version():
    try: return subprocess.check_output(["git","rev-parse","HEAD"],text=True,stderr=subprocess.DEVNULL).strip()
    except Exception: return "unknown"


def _markdown(report: dict) -> str:
    lines=[f"# Alpha Research Campaign {report['campaign_id']}","",f"- Dataset: `{report['dataset_id']}`",f"- Decision: **{report['decision']['decision']}**",f"- Hypotheses: {report['experiment_counts']['hypotheses']}",f"- Trials: {report['experiment_counts']['trials']}","", "## Research question", report["hypotheses"][0]["question"] if report["hypotheses"] else "No hypothesis", "", "## Results", "```json", json.dumps(report["results"],indent=2), "```", "", "## Limitations", "- Results are descriptive research evidence, not a probability or profitability claim.", "- Small campaigns do not establish generalisation, capacity, or predictive power.", "- Corporate actions, survivorship, and sector metadata require further hardening."]
    return "\n".join(lines)


def run_research_campaign(connection: sqlite3.Connection, *, dataset_id: str, universe: list[str], family: str, periods: dict, mode: str="STANDARD", experiment_budget: int=100, report_dir: str|None=None) -> dict:
    ensure_lab_tables(connection)
    if mode not in {"FAST","STANDARD","DEEP"}: raise ValueError("mode must be FAST, STANDARD, or DEEP")
    budgets={"FAST":min(experiment_budget,20),"STANDARD":min(experiment_budget,100),"DEEP":min(experiment_budget,500)}
    budget=budgets[mode]
    definition={"research_question":f"Controlled {family} hypothesis family on frozen data", "dataset_id":dataset_id,"universe":sorted({x.upper() for x in universe}),"train_period":list(periods["train"]),"validation_period":list(periods["validation"]),"test_period":list(periods["oos"]),"family":family,"mode":mode,"experiment_budget":budget,"oos_locked":True,"evaluation_version":"fixed-notional-v2-walk-forward","report_schema_version":2,"code_version":_code_version()}
    campaign=create_campaign(connection,definition)
    experiment=create_experiment(connection,campaign["campaign_id"],{"strategy_version":"laboratory-v1","parameters":{"family":family,"mode":mode},"dataset_id":dataset_id,"cost_model":{"fee_bps":1,"spread_bps":5,"slippage_bps":5},"slippage_model":{"bps":5},"engine_version":"daily-execution-v1"})
    transition_campaign(connection,campaign["campaign_id"],"DATA_READY"); transition_campaign(connection,campaign["campaign_id"],"RUNNING")
    symbols=definition["universe"]; all_rows={s:_bars(connection,s) for s in symbols}
    strategy_definition=StrategyDefinition(
        strategy_id=f"{family.lower()}-controlled", strategy_version="laboratory-v1",
        hypothesis=f"Controlled {family} hypothesis family on frozen data",
        universe=tuple(symbols), features=("daily_return","momentum","rolling_volatility"),
        signal_conditions=(f"family={family}",), entry_rules=("next_session_open",),
        exit_rules=("fixed_horizon",), holding_horizon=21,
        parameters={"family":family,"mode":mode}, position_sizing="fixed-notional research observation",
        transaction_cost_model={"fee_bps":1,"spread_bps":5,"slippage_bps":5},
        execution_assumptions={"next_session":True,"daily_bar_ambiguity":"conservative"})
    connection.execute("INSERT OR IGNORE INTO strategy_definitions VALUES(?,?,?,?,?)",(strategy_definition.strategy_fingerprint,strategy_definition.strategy_id,strategy_definition.strategy_version,json.dumps(strategy_definition.to_dict(),sort_keys=True),now()))
    hypotheses=generate_hypotheses(family,tuple([21,63,126,252] if family in {"MOMENTUM","CROSS_SECTIONAL"} else [20,50,100,200]),(5,21),budget)
    trials=[]; results={}
    for hypothesis in hypotheses:
        params_list=parameter_grid(family)
        for params in params_list:
            if len(trials)>=budget: break
            ticker_results=[]
            for symbol,rows in all_rows.items():
                parts=temporal_splits(rows,tuple(periods["train"]),tuple(periods["validation"]),tuple(periods["oos"]))
                metrics=score_candidate(parts["train"],family,params)
                ticker_results.append(metrics)
            metrics={"trades":sum(x["trades"] for x in ticker_results),"mean_return":sum(x["mean_return"] for x in ticker_results)/len(ticker_results) if ticker_results else 0.0,"max_drawdown":min((x["max_drawdown"] for x in ticker_results),default=0.0),"win_rate":sum(x["win_rate"] for x in ticker_results)/len(ticker_results) if ticker_results else 0.0}
            trial_id="TRIAL-"+uuid.uuid4().hex[:16].upper(); trials.append(metrics|{"trial_id":trial_id,"hypothesis_id":hypothesis["hypothesis_id"],"parameters":params})
            connection.execute("INSERT INTO laboratory_trials VALUES(?,?,?,?,?,?,?,?,?,?)",(trial_id,campaign["campaign_id"],experiment["experiment_id"],hypothesis["hypothesis_id"],None,"train",json.dumps(params,sort_keys=True),json.dumps(metrics,sort_keys=True),"COMPLETED",now()))
        if len(trials)>=budget: break
    ordered=sorted(trials,key=lambda x:x["mean_return"],reverse=True); best=ordered[0] if ordered else {"parameters":{"lookback":21,"horizon":5}}
    robustness_result={"parameter_surface":[],"cost_sensitivity":[],"positive_neighbor_fraction":0.0,"stable":False}
    if symbols:
        robustness_result=robustness(all_rows[symbols[0]],family,best["parameters"])
    gate=research_gate(best,robustness_result)
    # Validation and OOS run only for the selected frozen definition; no search uses OOS.
    selected={}
    walk_forward=[]
    for symbol,rows in all_rows.items():
        folds=walk_forward_folds(rows, periods["train"][0], periods["validation"][1], train_days=252, validation_days=63, step_days=63)
        walk_forward.append({"ticker":symbol,"folds":[{"fold":fold["fold"],"train_bars":len(fold["train"]),"validation_bars":len(fold["validation"]),"validation_metrics":score_candidate(fold["validation"],family,best["parameters"])} for fold in folds]})
    for split in ("validation","oos"):
        selected[split]=[]
        for symbol,rows in all_rows.items():
            parts=temporal_splits(rows,tuple(periods["train"]),tuple(periods["validation"]),tuple(periods["oos"]))
            selected[split].append({"ticker":symbol,"metrics":score_candidate(parts[split],family,best["parameters"])})
    report={"campaign_id":campaign["campaign_id"],"experiment_id":experiment["experiment_id"],"run_id":"RUN-"+uuid.uuid4().hex[:16].upper(),"dataset_id":dataset_id,"strategy_family":family,"mode":mode,"evaluation_version":"fixed-notional-v2-walk-forward","report_schema_version":2,"hypotheses":hypotheses,"best_trial":best,"results":{"baseline_buy_hold":baseline_metrics(next(iter(all_rows.values()),[]),best["parameters"].get("horizon",5)),"validation":selected["validation"],"walk_forward":walk_forward,"oos":selected["oos"]},"robustness":robustness_result,"multiple_testing":multiple_testing(trials),"decision":gate,"experiment_counts":{"hypotheses":len(hypotheses),"trials":len(trials),"budget":budget},"code_version":_code_version(),"limitations":["Event returns are fixed-notional observations; max drawdown is a cumulative-P&L proxy, not a compounded portfolio equity curve.","No DSR/PBO/CSCV claim is made; current diagnostics report trial distributions only.","Portfolio-level cross-sectional selection and corporate-action/delisting treatment remain limited."]}
    report["markdown"]=_markdown(report); report["html"]=html_report(report)
    connection.execute("INSERT INTO laboratory_reports VALUES(?,?,?,?,?)",(campaign["campaign_id"],json.dumps(report,sort_keys=True),report["markdown"],report["html"],now()))
    connection.execute("UPDATE experiments SET status=?,result_json=? WHERE experiment_id=?",("COMPLETED",json.dumps(report,sort_keys=True),experiment["experiment_id"]))
    transition_campaign(connection,campaign["campaign_id"],"VALIDATED" if gate["decision"]!="REJECTED" else "REJECTED")
    if report_dir:
        path=Path(report_dir); path.mkdir(parents=True,exist_ok=True); (path/(campaign["campaign_id"]+".json")).write_text(json.dumps(report,indent=2),encoding="utf-8"); (path/(campaign["campaign_id"]+".md")).write_text(report["markdown"],encoding="utf-8"); (path/(campaign["campaign_id"]+".html")).write_text(report["html"],encoding="utf-8")
    return report
