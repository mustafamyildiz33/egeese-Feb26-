# Paper Evaluation Specs

These JSON files define the phase-based paper demo suites that the paper runner
can execute with an exact active demo window of either 60 or 120 seconds.

## Phase layout

- `phase1`: Fair baseline / clean traffic comparison.
- `phase2`: Fire and bomb disagreement comparison.
- `phase3`: Hazard sensing / tornado sweep comparison.
- `phase4`: Adversarial stress / ghost outage plus noisy sensing comparison.

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
python3 paper_eval_runner.py --spec paper_eval/phase2/phase2_fire_60s.json --max-runs 2
```

Override node counts while testing:

```bash
python3 paper_eval_runner.py --spec paper_eval/phase4/phase4_stress_120s.json --max-runs 1 --node-counts 49
```

Short same-machine smoke test:

```bash
python3 paper_eval_runner.py --spec paper_eval/phase2/phase2_fire_60s.json --max-runs 1 --node-counts 49 --duration-sec 10
```

## Copy-Paste Commands

## Demo Order

Use this order during class:

1. Start a quick `4-batch` run.
2. In a second terminal, tail the live event stream.
3. In a third terminal, tail one or two node logs.
4. When it finishes, open the campaign report.
5. Open the latest scenario suite report.
6. Open the latest single-run deep dive.

### Live Tail Commands

Tail the newest run's event stream:

```bash
cd /Users/mustafa/egess
RUN_DIR=$(ls -1dt runs/* | head -n 1)
tail -f "$RUN_DIR/paper_events.jsonl"
```

Tail the newest run's local and far watch node logs:

```bash
cd /Users/mustafa/egess
RUN_DIR=$(ls -1dt runs/* | head -n 1)
tail -f "$RUN_DIR/node_9024.log" "$RUN_DIR/node_9000.log"
```

Tail the newest run's paper summary files after the run:

```bash
cd /Users/mustafa/egess
RUN_DIR=$(ls -1dt runs/* | head -n 1)
sed -n '1,40p' "$RUN_DIR/paper_summary.tsv"
sed -n '1,40p' "$RUN_DIR/paper_watch_nodes.tsv"
```

### Quick Test: 4 batches, 60 seconds, 49 nodes

Run the quick all-scenarios test:

```bash
cd /Users/mustafa/egess
./run_paper_eval.sh --mode all --duration 60 --batches 4 --nodes 49
```

Open the campaign report:

```bash
cd /Users/mustafa/egess
CAMPAIGN_DIR=$(ls -1dt campaign_reports/all_together_60s_* | head -n 1)
open "$CAMPAIGN_DIR/index.html"
```

Open the latest scenario suite report:

```bash
cd /Users/mustafa/egess
REPORT_DIR=$(ls -1dt paper_reports/* | head -n 1)
open "$REPORT_DIR/index.html"
```

Open the latest single-run deep dive:

```bash
cd /Users/mustafa/egess
RUN_DIR=$(ls -1dt runs/* | head -n 1)
open "$RUN_DIR/paper_summary.html"
```

### Quick Test: 4 batches, 60 seconds, 40 nodes

```bash
cd /Users/mustafa/egess
./run_paper_eval.sh --mode all --duration 60 --batches 4 --nodes 40
```

### Quick Test: 4 batches, 60 seconds, 64 nodes

```bash
cd /Users/mustafa/egess
./run_paper_eval.sh --mode all --duration 60 --batches 4 --nodes 64
```

### Quick Test: 4 batches, 60 seconds, 89 nodes

```bash
cd /Users/mustafa/egess
./run_paper_eval.sh --mode all --duration 60 --batches 4 --nodes 89
```

### Full Run: 30 batches, 60 seconds, 49 nodes

Run the full all-scenarios paper batch:

```bash
cd /Users/mustafa/egess
./run_paper_eval.sh --mode all --duration 60 --batches 30 --nodes 49
```

Open the campaign report:

```bash
cd /Users/mustafa/egess
CAMPAIGN_DIR=$(ls -1dt campaign_reports/all_together_60s_* | head -n 1)
open "$CAMPAIGN_DIR/index.html"
```

Open the latest scenario suite report:

```bash
cd /Users/mustafa/egess
REPORT_DIR=$(ls -1dt paper_reports/* | head -n 1)
open "$REPORT_DIR/index.html"
```

Open the latest single-run deep dive:

```bash
cd /Users/mustafa/egess
RUN_DIR=$(ls -1dt runs/* | head -n 1)
open "$RUN_DIR/paper_summary.html"
```

### Full Run: 30 batches, 60 seconds, 40 nodes

```bash
cd /Users/mustafa/egess
./run_paper_eval.sh --mode all --duration 60 --batches 30 --nodes 40
```

### Full Run: 30 batches, 60 seconds, 64 nodes

```bash
cd /Users/mustafa/egess
./run_paper_eval.sh --mode all --duration 60 --batches 30 --nodes 64
```

### Full Run: 30 batches, 60 seconds, 89 nodes

```bash
cd /Users/mustafa/egess
./run_paper_eval.sh --mode all --duration 60 --batches 30 --nodes 89
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

## Cross-Protocol Merge

If EGESS and Check-In are run on different computers, copy both `paper_reports/`
folders onto one machine and generate the final comparison page there:

```bash
python3 cross_protocol_summary.py \
  --egess-root /path/to/egess/paper_reports \
  --checkin-root /path/to/checkin/paper_reports
```

That produces:

- `comparison_reports/<timestamp>/index.html`
- `comparison_reports/<timestamp>/cross_protocol_overview.tsv`
- `comparison_reports/<timestamp>/combined_<scenario>.tsv`
- `comparison_reports/<timestamp>/figure_exports/*.png`
- `comparison_reports/<timestamp>/figure_exports/*.tsv`
