"""Run: ./.venv/bin/python -m eval [--live] [--output report.json]."""
import argparse
import asyncio
import json
import tempfile
from pathlib import Path
from collections import defaultdict
from data.dossier_loader import list_dossiers, load_for_pipeline
from ledger import LedgerStore
from ledger.seed import submit_dossier
from pipeline.graph import run_triage
from registry.loader import load_all_rulesets
from agents.catalog import RULESET_LOADERS
from agents.assess import current


def metrics(expected, detected):
    tp, fp, fn = len(expected & detected), len(detected - expected), len(expected - detected)
    return dict(tp=tp, fp=fp, fn=fn, precision=tp/(tp+fp) if tp+fp else None,
                recall=tp/(tp+fn) if tp+fn else None)


async def evaluate(*, live=False):
    rules = {r.rule_id: r for rs in load_all_rulesets().values() for r in rs.rules}
    # These labelled outcomes require judgment; regex candidate detection is
    # reported as triage detection, never proof that the agent acted.
    judged_only = {'F49', 'F55', 'F38'}
    expected, detected, clean, adverse = set(), set(), set(), set()
    owned_rules = {name: {r.rule_id for r in rs.rules} for name, loader in RULESET_LOADERS.items() if (rs := loader()) is not None}
    by_agent = defaultdict(set)
    by_rule = defaultdict(set)
    unknown, judgments, submissions = [], [], []
    with tempfile.TemporaryDirectory(prefix='mandate-eval-') as directory:
        store = LedgerStore(Path(directory) / 'ledger.db')
        for path in list_dossiers():
            dossier = load_for_pipeline(path)
            cid = submit_dossier(store, dossier)
            record = await run_triage(cid, store=store, deterministic_only=not live)
            # Open labels only AFTER the production graph has returned.
            labels = json.loads((path / 'ground_truth.json').read_text())
            clean |= {(cid, rid) for rid in labels['clean_runs']}
            for p in labels['planted']:
                failure = p['failure']
                if failure.startswith('S'):
                    submissions.append({'dossier_id': cid, **p}); continue
                if failure in judged_only:
                    judgments.append({'dossier_id': cid, **p, 'evaluated': live})
                    if not live: continue
                owners = [r for r in rules.values() if failure in r.failures and r.status == 'active']
                if not owners: unknown.append({'dossier_id': cid, **p})
                expected.add((cid, p.get('run_ref'), failure))
            for f in record.facts:
                if f.kind != 'breach' or f.rule_id not in rules: continue
                for failure in rules[f.rule_id].failures:
                    if failure in judged_only: continue
                    if failure == 'F19' and not f.values.get('observed_blocklisted'): continue
                    key = (cid, f.run_ref, failure)
                    detected.add(key); by_agent[f.domain].add(key); by_rule[f.rule_id].add(key)
            for a in current(record.assessments):
                if a.verdict != 'breach' or a.rule_id not in rules: continue
                for failure in set(rules[a.rule_id].failures) - judged_only:
                    # F19 denotes observed use of a blocklisted model, not a
                    # declaration mismatch. Its mechanical evidence must say so.
                    if failure == 'F19' and not any(f.fact_id in a.fact_ids and f.values.get('observed_blocklisted') for f in record.facts): continue
                    adverse.update((cid, rid, failure) for rid in a.run_refs or [None])
            if live:
                for a in current(record.assessments):
                    if a.verdict != 'breach' or a.rule_id not in rules: continue
                    for failure in set(rules[a.rule_id].failures) & judged_only:
                        for rid in a.run_refs or [None]:
                            key = (cid, rid, failure)
                            detected.add(key); by_agent[a.agent].add(key); by_rule[a.rule_id].add(key)
        false_clean = clean & {(cid, rid) for cid, rid, _ in detected}
        return {'mode': 'live' if live else 'mechanical', 'overall': metrics(expected, detected),
                'adverse_assessments': metrics(expected, adverse),
                'adverse_false_positive_clean_runs': len(clean & {(cid, rid) for cid, rid, _ in adverse}),
                'clean_runs': len(clean), 'false_positive_clean_runs': len(false_clean),
                'false_positive_rate': len(false_clean)/len(clean),
                'missed': sorted(expected-detected, key=str), 'unexpected': sorted(detected-expected, key=str),
                'per_failure': {f: metrics({k for k in expected if k[2] == f}, {k for k in detected if k[2] == f})
                                for f in sorted({k[2] for k in expected | detected})},
                'per_agent': {agent: metrics({k for k in expected if any(k[2] in rules[rid].failures for rid in ids)}, by_agent[agent]) for agent, ids in owned_rules.items()},
                'per_rule': {rid: metrics({k for k in expected if k[2] in rules[rid].failures}, values)
                             for rid, values in by_rule.items()},
                'judged': judgments, 'submission_labels': submissions, 'awaiting_specialist': unknown,
                'coverage_note': 'Failure labels are not exhaustive per-rule annotations. Per-rule metrics inherit owning failure labels and are diagnostic, not independent validation. Mechanical breaches include successfully blocked attempts; adverse assessments report those separately. F32 candidate detection is not proof of acting on an injection. Corpus coverage is not coverage of all 73 failures.',
                'ledger_integrity': store.verify()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = asyncio.run(evaluate(live=args.live))
    rendered = json.dumps(report, indent=2)
    if args.output: args.output.write_text(rendered + '\n')
    print(rendered)
    raise SystemExit(1 if report['awaiting_specialist'] or report['ledger_integrity'] or report['overall']['fn'] else 0)


if __name__ == '__main__': main()
