"""Rule-based anomaly detector and comparison with independent ground truth.

Findings are matched to labels using (record_id, issue_type, source_record_id),
so two anomalies on different order lines in one payout remain distinguishable.
"""
import argparse
import json
from pathlib import Path

import pandas as pd

from src.common import write_json


def evaluate(data_dir):
    d = Path(data_dir)

    def read(name):
        return pd.read_csv(d / f"{name}.csv", keep_default_na=False)

    listings = read("product_listings")
    sellers = read("sellers")
    fulfillments = read("fulfillments")
    lines = read("order_lines")
    payouts = read("payouts")
    payout_lines = read("payout_lines")
    disputes = read("disputes")
    ground_truth = read("ground_truth")
    findings = []

    def add(entity_type, record_id, issue_type, source_record_id=""):
        findings.append({
            "entity_type": entity_type,
            "record_id": str(record_id),
            "issue_type": issue_type,
            "source_record_id": "" if source_record_id is None else str(source_record_id),
        })

    # 1. A listing created after suspension must not be active.
    seller_lookup = sellers.set_index("seller_id").to_dict("index")
    for listing in listings.itertuples(index=False):
        seller = seller_lookup.get(listing.seller_id, {})
        suspended_at = seller.get("suspended_at", "")
        if (seller.get("status") == "suspended" and listing.status == "active"
                and suspended_at and listing.created_at > suspended_at):
            add("product_listing", listing.listing_id, "suspended_seller_listing", listing.seller_id)

    # Operational alert: late shipments are also labeled in ground truth.
    for f in fulfillments.itertuples(index=False):
        if f.shipped_at and f.expected_ship_at and f.shipped_at > f.expected_ship_at:
            add("fulfillment", f.fulfillment_id, "late_shipment")

    # 2. Payout total must reconcile exactly to the sum of payout lines.
    amount_values = pd.to_numeric(payout_lines["amount_cents"], errors="coerce").fillna(0).astype("int64")
    sums = payout_lines.assign(_amount=amount_values).groupby("payout_id")["_amount"].sum().to_dict()
    for p in payouts.itertuples(index=False):
        if int(sums.get(p.payout_id, 0)) != int(p.recorded_total_cents):
            add("payout", p.payout_id, "payout_total_mismatch")

    # 3. A payout must not include duplicate commission entries for one order line.
    commission_rows = payout_lines[payout_lines.line_type == "commission"]
    duplicate_groups = commission_rows.groupby(["payout_id", "order_line_id"], dropna=False).size()
    for (payout_id, order_line_id), count in duplicate_groups.items():
        if count > 1:
            add("payout_line", payout_id, "commission_applied_twice", order_line_id)

    # 4. Payout date must be on or after delivery + the seven-day hold.
    fulfillment_by_line = fulfillments.set_index("order_line_id").to_dict("index")
    payout_date_by_id = payouts.set_index("payout_id").payout_date.to_dict()
    sale_rows = payout_lines[payout_lines.line_type == "sale"]
    for row in sale_rows.itertuples(index=False):
        f = fulfillment_by_line.get(row.order_line_id)
        payout_date = payout_date_by_id.get(row.payout_id, "")
        delivered_at = f.get("delivered_at", "") if f else ""
        if not payout_date or not delivered_at:
            continue
        release_at = pd.to_datetime(delivered_at) + pd.Timedelta(days=7)
        if pd.to_datetime(payout_date) < release_at:
            add("payout", row.payout_id, "payout_before_hold_release", row.order_line_id)

    # 5. Every lost/resolved dispute attached to a paid order must have its own
    # negative dispute line. dispute_id on payout_lines makes this auditable.
    order_lines_by_order = lines.groupby("order_id").order_line_id.apply(list).to_dict()
    payout_ids_by_line = sale_rows.groupby("order_line_id").payout_id.apply(list).to_dict()
    dispute_line_pairs = set(
        (str(r.payout_id), str(r.dispute_id))
        for r in payout_lines.itertuples(index=False)
        if r.line_type == "dispute" and r.dispute_id and int(r.amount_cents) < 0
    )
    for dispute in disputes.itertuples(index=False):
        if dispute.status not in ("lost", "resolved"):
            continue
        order_line_ids = order_lines_by_order.get(dispute.order_id, [])
        relevant_payouts = sorted({pid for olid in order_line_ids for pid in payout_ids_by_line.get(olid, [])})
        # No payout means there is no payout deduction to audit yet.
        for payout_id in relevant_payouts:
            if (str(payout_id), str(dispute.dispute_id)) not in dispute_line_pairs:
                add("dispute", dispute.dispute_id, "dispute_not_deducted", dispute.order_id)
                break

    columns = ["entity_type", "record_id", "issue_type", "source_record_id"]
    findings_df = pd.DataFrame(findings, columns=columns)
    findings_df = findings_df.drop_duplicates(subset=columns).sort_values(columns).reset_index(drop=True)
    findings_df.to_csv(d / "detected_anomalies.csv", index=False)

    def keys(df):
        if df.empty:
            return set()
        return set(zip(df.record_id.astype(str), df.issue_type.astype(str), df.source_record_id.astype(str)))

    truth_keys = keys(ground_truth)
    predicted_keys = keys(findings_df)
    true_positives = len(truth_keys & predicted_keys)
    false_positives = len(predicted_keys - truth_keys)
    false_negatives = len(truth_keys - predicted_keys)
    precision = true_positives / (true_positives + false_positives) if true_positives + false_positives else 0.0
    recall = true_positives / (true_positives + false_negatives) if true_positives + false_negatives else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    report = {
        "detected_findings": int(len(findings_df)),
        "ground_truth_labels": int(len(ground_truth)),
        "matched_keys": true_positives,
        "false_positive_keys": false_positives,
        "false_negative_keys": false_negatives,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "detected_issue_counts": findings_df.issue_type.value_counts().to_dict() if len(findings_df) else {},
        "matching_key": ["record_id", "issue_type", "source_record_id"],
    }
    write_json(d / "evaluation_report.json", report)
    print(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="outputs/small")
    args = parser.parse_args()
    evaluate(args.data)


if __name__ == "__main__":
    main()
