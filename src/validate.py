"""Relational and arithmetic validation for generated exports."""
import argparse, json
from pathlib import Path
import pandas as pd
from src.common import write_json

def validate(data_dir):
    d=Path(data_dir)
    def read(n): return pd.read_csv(d/f"{n}.csv", keep_default_na=False)
    names=["sellers","product_listings","orders","order_lines","fulfillments","customer_reviews","disputes","commission_rules","payouts","payout_lines"]
    tables={n:read(n) for n in names}
    errors=[]; checks={}
    pk_cols={"sellers":"seller_id","product_listings":"listing_id","orders":"order_id","order_lines":"order_line_id",
             "fulfillments":"fulfillment_id","customer_reviews":"review_id","disputes":"dispute_id",
             "commission_rules":"rule_id","payouts":"payout_id","payout_lines":"payout_line_id"}
    for n,pk in pk_cols.items():
        dup=int(tables[n][pk].duplicated().sum())
        checks[f"{n}.primary_key_duplicates"]=dup
        if dup: errors.append(f"{n}: {dup} duplicate {pk}")
    fk_specs=[
        ("product_listings","seller_id","sellers","seller_id"),
        ("order_lines","order_id","orders","order_id"),
        ("order_lines","listing_id","product_listings","listing_id"),
        ("order_lines","seller_id","sellers","seller_id"),
        ("fulfillments","order_line_id","order_lines","order_line_id"),
        ("customer_reviews","order_line_id","order_lines","order_line_id"),
        ("disputes","order_id","orders","order_id"),
        ("payouts","seller_id","sellers","seller_id"),
        ("payout_lines","payout_id","payouts","payout_id"),
    ]
    for child,field,parent,pfield in fk_specs:
        invalid=int((~tables[child][field].isin(set(tables[parent][pfield]))).sum())
        checks[f"{child}.{field}_invalid_fk"]=invalid
        if invalid: errors.append(f"{child}: {invalid} invalid {field} foreign keys")
    nonempty_dispute_ids = tables["payout_lines"].loc[tables["payout_lines"].dispute_id != "", "dispute_id"]
    invalid_dispute_refs = int((~nonempty_dispute_ids.isin(set(tables["disputes"].dispute_id))).sum())
    checks["payout_lines.dispute_id_invalid_fk"] = invalid_dispute_refs
    if invalid_dispute_refs: errors.append(f"payout_lines: {invalid_dispute_refs} invalid dispute_id foreign keys")
    checks["fulfillment.order_line_duplicates"]=int(tables["fulfillments"]["order_line_id"].duplicated().sum())
    if checks["fulfillment.order_line_duplicates"]: errors.append("Fulfillment has duplicate order_line_id")
    # Order totals
    line_sums=tables["order_lines"].assign(line_total_cents=lambda x: pd.to_numeric(x.line_total_cents)).groupby("order_id").line_total_cents.sum()
    order_totals=tables["orders"].set_index("order_id").order_total_cents.astype(int)
    mismatches=int(sum(int(line_sums.get(oid,0)) != int(total) for oid,total in order_totals.items()))
    checks["orders.total_mismatches"]=mismatches
    if mismatches: errors.append(f"{mismatches} order totals do not equal line sums")
    # Payout sums: intentionally anomalous payouts should be detected.
    lines=tables["payout_lines"].assign(amount_cents=lambda x: pd.to_numeric(x.amount_cents))
    sums=lines.groupby("payout_id").amount_cents.sum()
    payouts=tables["payouts"].set_index("payout_id").recorded_total_cents.astype(int)
    mismatch_ids=[pid for pid,total in payouts.items() if int(sums.get(pid,0)) != int(total)]
    checks["payouts.total_mismatches_detected"]=len(mismatch_ids)
    checks["payouts.mismatch_ids_sample"]=mismatch_ids[:20]
    # Enum/date and baseline counts
    allowed={"seller_status":{"active","suspended","onboarding"},"listing_status":{"active","inactive","removed"},
             "fulfillment_status":{"pending","shipped","delivered","returned"}}
    for key,vals,field in [( "seller_status",allowed["seller_status"],"status")]:
        bad=int((~tables["sellers"][field].isin(vals)).sum()); checks[f"{key}.invalid_enum"]=bad
        if bad: errors.append(f"Invalid seller status values: {bad}")
    gt=read("ground_truth")
    checks["ground_truth.rows"]=len(gt)
    checks["ground_truth.issue_types"]=gt.issue_type.value_counts().to_dict() if len(gt) else {}
    report={"passed":len(errors)==0,"errors":errors,"checks":checks,"notes":["Payout total mismatches are expected injected anomalies and are reported, not treated as generator failures.","Ground truth is never used to calculate detector findings."]}
    write_json(d/"validation_report.json",report)
    print(json.dumps(report,indent=2))
    return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--data",default="outputs/small")
    args=ap.parse_args(); report=validate(args.data)
    raise SystemExit(0 if report["passed"] else 1)
if __name__=="__main__": main()
