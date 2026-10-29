# Changelog

## 1.1.0
- Corrected payout dates: normal seller/order payouts occur after all included seven-day hold releases; intentional early payouts are scoped to the affected order batch.
- Corrected duplicate-commission detection at the payout/order-line level.
- Prevented ordinary active listings created after suspension from being generated as accidental anomalies; injected cases remain explicitly labeled.
- Added `dispute_id` to payout lines and made dispute deduction detection trace each lost/resolved dispute to its own negative payout line.
- Kept injected anomaly labels only in `ground_truth.csv`; removed diagnostic `issue_type` fields from source tables.
- Added ground-truth labels for late-shipment operational alerts and matched evaluation on record ID, issue type, and source record ID.
- Added nullable dispute foreign-key validation and regression tests.
