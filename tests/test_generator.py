from pathlib import Path
import pandas as pd
from src.generate import make_data
from src.validate import validate
from src.evaluate import evaluate

def test_small_generation_and_integrity(tmp_path):
    out=tmp_path/"data"
    make_data("small",20261022,out)
    assert len(pd.read_csv(out/"sellers.csv"))==50
    assert len(pd.read_csv(out/"product_listings.csv"))==250
    assert len(pd.read_csv(out/"orders.csv"))==1000
    report=validate(out)
    assert report["checks"]["sellers.primary_key_duplicates"]==0
    assert report["checks"]["order_lines.order_id_invalid_fk"]==0
    evaluate(out)
    assert (out/"detected_anomalies.csv").exists()

def test_fixed_seed_reproducibility(tmp_path):
    a=tmp_path/"a"; b=tmp_path/"b"
    make_data("small",20261022,a); make_data("small",20261022,b)
    for name in ["sellers.csv","product_listings.csv","orders.csv","order_lines.csv","ground_truth.csv"]:
        assert (a/name).read_bytes()==(b/name).read_bytes()

def test_all_injected_anomalies_are_detected_without_false_positives(tmp_path):
    out = tmp_path / "audit_data"
    make_data("small", 20261022, out)
    report = evaluate(out)
    required = {
        "payout_before_hold_release",
        "commission_applied_twice",
        "suspended_seller_listing",
        "dispute_not_deducted",
        "payout_total_mismatch",
    }
    ground_truth = pd.read_csv(out / "ground_truth.csv", keep_default_na=False)
    findings = pd.read_csv(out / "detected_anomalies.csv", keep_default_na=False)
    assert required.issubset(set(ground_truth.issue_type))
    assert required.issubset(set(findings.issue_type))
    assert report["false_positive_keys"] == 0
    assert report["false_negative_keys"] == 0
    assert report["precision"] == 1.0
    assert report["recall"] == 1.0
    assert report["f1"] == 1.0
    payout_lines = pd.read_csv(out / "payout_lines.csv", keep_default_na=False)
    assert "dispute_id" in payout_lines.columns
    assert "issue_type" not in pd.read_csv(out / "product_listings.csv").columns
    assert "issue_type" not in pd.read_csv(out / "disputes.csv").columns
    assert "issue_type" not in pd.read_csv(out / "fulfillments.csv").columns
    validation = validate(out)
    assert validation["passed"] is True
    assert validation["checks"]["payout_lines.dispute_id_invalid_fk"] == 0
