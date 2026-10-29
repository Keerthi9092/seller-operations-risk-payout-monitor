# Architecture and reproducibility

1. `src.generate` creates master data, then order/line/fulfillment records, reviews/disputes, rules, payout lines and a separate ground-truth label file.
2. `src.validate` checks primary keys, foreign keys, order totals and payout reconciliation.
3. `src.evaluate` runs rule-based detectors without reading ground truth until the evaluation comparison stage.
4. `dashboard.py` visualizes seller, fulfillment, payout and anomaly summaries.

## Reproducibility
The generator seeds both NumPy and Python's `random` module. IDs use deterministic counters. Run the same scale and seed twice into different folders and compare checksums:
```powershell
python -m src.generate --scale small --seed 20261022 --out outputs/run_a
python -m src.generate --scale small --seed 20261022 --out outputs/run_b
python -m src.validate --data outputs/run_a
python -m src.evaluate --data outputs/run_a
```
Compare `checksums.json` for generated CSVs. Output manifests intentionally avoid a wall-clock generation timestamp to keep artifacts reproducible.

## Known starter limitations
- Financial policy is illustrative and must be reviewed before production.
- Base generator uses one fulfillment per order line; extend if modeling multiple parcels per line.
- Payouts are grouped by seller and order for the generated batch, rather than modeled as a real payout calendar.
- Injected anomaly labels are kept only in `ground_truth.csv`, not exposed as `issue_type` columns in source tables.
- Each payout line can carry a nullable `dispute_id`, so a missing deduction is evaluated against the specific dispute rather than merely checking whether any negative dispute line exists.
- Payout dates are generated after all hold releases for normal payouts; selected early payouts are labeled at the line level for every line actually affected.
- Full-scale run should be validated on the target machine for runtime and memory.
