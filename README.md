# Seller Operations, Risk & Payout Monitoring

A reproducible synthetic-data project for the 72 Hours Code Challenge. It generates marketplace master and transaction data, calculates seller/financial metrics, detects five required anomaly classes, and exports CSV/JSON plus a validation report.

## Requirements
- Python 3.10+
- Optional: MySQL server and Workbench. The project runs locally without MySQL by default.

## Setup (Windows PowerShell)
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```
If PowerShell blocks activation, use Command Prompt:
```bat
.venv\Scripts\activate.bat
```

## Generate a small starter dataset
```bash
python -m src.generate --scale small --seed 20261022 --out outputs/small
```

## Generate the challenge-sized dataset
```bash
python -m src.generate --scale full --seed 20261022 --out outputs/full
```
Full scale targets 2,000 sellers, 20,000 listings, 100,000 orders and 10,000 disputes. It may take a few minutes and use significant disk space. `--scale small` uses the same generation logic at a smaller volume.

## Validate / evaluate
```bash
python -m src.validate --data outputs/small
python -m src.evaluate --data outputs/small
pytest -q
```

## Launch dashboard
```bash
streamlit run dashboard.py
```
The dashboard reads `outputs/small` by default; choose another output directory in the sidebar. Generate a dataset first.

## MySQL (optional)
The CSVs are portable. Create a database in MySQL Workbench, then use `schema.sql` to create the normalized core tables. For the challenge, the generated CSVs are the source-of-truth export; this starter does not automatically bulk-load the full dataset into MySQL. You can extend it with SQLAlchemy or `LOAD DATA LOCAL INFILE` after reviewing your server's permissions.

## Output files
- `sellers.csv`, `product_listings.csv`, `orders.csv`, `order_lines.csv`, `fulfillments.csv`
- `customer_reviews.csv`, `disputes.csv`, `commission_rules.csv`, `payouts.csv`, `payout_lines.csv`
- `seller_events.csv`, `fulfillment_events.csv`
- `ground_truth.csv` (expected anomaly labels only; never used as detector input)
- `manifest.json`, `validation_summary.json`, `checksums.json`
- JSON exports of core entities in `json/`

## Important design notes
- Synthetic records only; no personal/customer real-world data is used.
- IDs are deterministic and immutable for a fixed seed and scale.
- Ground-truth anomalies are generated separately from detector outputs; source tables do not expose injected `issue_type` labels.
- Financial values use integer cents in generation to avoid floating-point money arithmetic.
- The generator intentionally injects labeled anomalies into selected records so detectors can be evaluated.
- Payout lines include a nullable `dispute_id`, allowing each dispute deduction to be audited independently.

## Detector coverage and evaluation
The rule-based detector checks payout timing against delivery plus the seven-day hold, duplicate commissions per order line, active listings created after seller suspension, missing deductions for lost/resolved disputes, and payout totals that do not reconcile to their lines. It also reports late shipments as a separate operational alert.

Run the checks after generating data:
```powershell
python -m src.generate --scale small --seed 20261022 --out outputs/small
python -m src.validate --data outputs/small
python -m src.evaluate --data outputs/small
python -m pytest -q
```

Evaluation matches findings against labels using `record_id`, `issue_type`, and `source_record_id` so line-level issues within the same payout are distinguished. On the bundled seed-20261022 small dataset, expected evaluation is precision 1.0, recall 1.0, and F1 1.0. These scores verify the synthetic injected cases and are not a claim of performance on real marketplace data.
- This is a challenge starter implementation, not a production payment processor. Review business/legal policies before using real money or customer data.
