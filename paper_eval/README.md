# Paper Evaluation Specs

These JSON files define the phase-based paper demo suites that the paper runner
can execute with an exact active demo window of either 60 or 120 seconds.

## Phase layout

- `phase1`: Fair baseline / clean traffic comparison.
- `phase2`: Hazard sensing / tornado sweep comparison.
- `phase3`: Adversarial stress / ghost outage plus noisy sensing comparison.

## Durations

Each phase includes:

- a `60s` spec for the exact one-minute runs your teammate requested,
- a `120s` spec for the two-minute comparison run you may want later.

## Runner examples

Dry-run a suite without starting nodes:

```bash
python3 paper_eval_runner.py --spec paper_eval/phase1/phase1_baseline_60s.json --dry-run
```

Run one suite with only the first two repetitions while testing:

```bash
python3 paper_eval_runner.py --spec paper_eval/phase2/phase2_hazard_60s.json --max-runs 2
```

Override node counts while testing:

```bash
python3 paper_eval_runner.py --spec paper_eval/phase3/phase3_stress_120s.json --max-runs 1 --node-counts 49
```

Short same-machine smoke test:

```bash
python3 paper_eval_runner.py --spec paper_eval/phase2/phase2_hazard_60s.json --max-runs 1 --node-counts 49 --duration-sec 10
```

## Output

Each real run writes:

- `runs/<timestamp>/paper_events.jsonl`
- `runs/<timestamp>/paper_manifest.json`
- `runs/<timestamp>/paper_evidence.json`
- `runs/<timestamp>/paper_summary.tsv`
- `runs/<timestamp>/paper_watch_nodes.tsv`
- `runs/<timestamp>/paper_summary.md`

Each suite also writes a combined report bundle into `paper_reports/<suite_id>_<timestamp>/`.
