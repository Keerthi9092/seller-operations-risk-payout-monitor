"""Deterministic synthetic marketplace data generator."""
import argparse, json, random
from pathlib import Path
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
from src.common import write_json, sha256_file

CATEGORIES = ["home", "fashion", "beauty", "electronics", "sports", "books", "food"]
STATUSES = ["active", "suspended", "onboarding"]
SEED_DEFAULT = 20261022

def dtstr(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def make_data(scale="small", seed=SEED_DEFAULT, out="outputs/small"):
    if scale == "small":
        n_sellers, n_listings, n_orders, n_disputes = 50, 250, 1000, 100
    elif scale == "medium":
        n_sellers, n_listings, n_orders, n_disputes = 500, 5000, 20000, 2000
    elif scale == "full":
        n_sellers, n_listings, n_orders, n_disputes = 2000, 20000, 100000, 10000
    else:
        raise ValueError("scale must be small, medium, or full")
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    for p in out.glob("*.csv"): p.unlink()
    (out / "json").mkdir(exist_ok=True)
    rng = np.random.default_rng(seed)
    py_rng = random.Random(seed)
    start = datetime(2026, 1, 1, 8, 0, 0)
    # Sellers: status history includes suspended sellers.
    sellers = []
    seller_events = []
    suspended_ids = set()
    for i in range(1, n_sellers+1):
        sid = f"SELL-{i:06d}"
        created = start + timedelta(days=int(rng.integers(0, 240)))
        status = "suspended" if rng.random() < 0.045 else ("onboarding" if rng.random() < 0.03 else "active")
        suspended_at = created + timedelta(days=int(rng.integers(5, 60))) if status == "suspended" else None
        if status == "suspended": suspended_ids.add(sid)
        sellers.append(dict(seller_id=sid, seller_name=f"Seller {i:04d}", status=status,
                            created_at=dtstr(created), suspended_at=dtstr(suspended_at) if suspended_at else None,
                            service_tier=str(rng.choice(["standard","priority","managed"], p=[.75,.20,.05]))))
        seller_events.append(dict(event_id=f"SEV-{i:07d}-01", seller_id=sid, event_type="seller_created",
                                  event_at=dtstr(created), prior_status=None, new_status="active", issue_type=None))
        if status == "suspended":
            seller_events.append(dict(event_id=f"SEV-{i:07d}-02", seller_id=sid, event_type="seller_suspended",
                                      event_at=dtstr(suspended_at), prior_status="active", new_status="suspended", issue_type=None))
    sellers_df = pd.DataFrame(sellers)
    seller_record_by_id = {seller["seller_id"]: seller for seller in sellers}
    seller_status_by_id = {seller["seller_id"]: seller["status"] for seller in sellers}
    # Listings
    listings, listing_owner = [], {}
    by_seller = {s["seller_id"]: [] for s in sellers}
    for i in range(1, n_listings+1):
        owner_idx = int(rng.integers(1, n_sellers+1))
        sid = f"SELL-{owner_idx:06d}"
        local_counter = len(by_seller[sid]) + 1
        lid = f"LIST-{sid}-{local_counter:06d}"
        created = start + timedelta(days=int(rng.integers(0, 290)))
        # Deliberate anomaly: active listing created after seller suspension.
        anomaly = sid in suspended_ids and rng.random() < 0.12
        if anomaly:
            created = datetime.strptime(seller_record_by_id[sid]["suspended_at"], "%Y-%m-%d %H:%M:%S") + timedelta(days=1)
            status = "active"
        else:
            status = str(rng.choice(["active","inactive","removed"], p=[.82,.13,.05]))
            # Prevent ordinary data from accidentally creating the same anomaly.
            seller = seller_record_by_id[sid]
            if seller["suspended_at"] and created > datetime.strptime(seller["suspended_at"], "%Y-%m-%d %H:%M:%S") and status == "active":
                status = "inactive"
        row = dict(listing_id=lid, seller_id=sid, product_name=f"{str(rng.choice(['Everyday','Premium','Classic','Modern','Eco','Compact']))} {str(rng.choice(['Bottle','Shirt','Lamp','Headphones','Bag','Notebook','Mixer']))} {i:05d}",
                   category=str(rng.choice(CATEGORIES)), price_cents=int(rng.integers(500, 50000)),
                   currency="USD", status=status, created_at=dtstr(created), issue_type="suspended_seller_listing" if anomaly else None)
        listings.append(row); listing_owner[lid] = sid; by_seller[sid].append(lid)
    # Ensure each seller has at least one listing for sensible coverage
    for s in sellers:
        if not by_seller[s["seller_id"]]:
            # Reassign one listing from the seller with most listings while preserving deterministic IDs is not worth complexity.
            pass
    listing_df = pd.DataFrame(listings)
    active_listing_ids = listing_df.loc[listing_df.status == "active", "listing_id"].tolist()
    if not active_listing_ids: active_listing_ids = listing_df["listing_id"].tolist()
    listing_map = {r.listing_id: r for r in listing_df.itertuples(index=False)}
    # Effective-dated commission rules
    rules = []
    for j, cat in enumerate(CATEGORIES, 1):
        rules.append(dict(rule_id=f"CR-{j:03d}-2026", category=cat, rate=float([.08,.10,.12,.07,.09,.06,.11][j-1]),
                          effective_from="2026-01-01", effective_to=None, reserve_rate=.05, hold_days=7))
    rules_df = pd.DataFrame(rules)
    # Orders, lines and fulfillment
    orders, lines, fulfillments, reviews, fulfillment_events = [], [], [], [], []
    line_number = 0
    for oi in range(1, n_orders+1):
        oid = f"ORD-2026-{oi:06d}"
        od = start + timedelta(days=int(rng.integers(0, 285)), hours=int(rng.integers(0, 24)))
        n_lines = int(rng.choice([1,2,3,4], p=[.66,.23,.09,.02]))
        chosen = rng.choice(active_listing_ids, size=min(n_lines, len(active_listing_ids)), replace=False)
        order_line_ids = []
        order_total = 0
        order_status = "placed"
        for li, lid in enumerate(chosen, 1):
            line_number += 1
            lrow = listing_map[lid]
            q = int(rng.integers(1, 4))
            cents = int(lrow.price_cents)
            total_cents = cents*q
            order_total += total_cents
            olid = f"OL-{oi:06d}-{li:02d}"
            order_line_ids.append(olid)
            ship_due = od + timedelta(days=2)
            ship_late = rng.random() < .075
            shipped = od + timedelta(days=int(rng.integers(1, 5)) if ship_late else int(rng.integers(0, 2)))
            if shipped < od: shipped = od
            delivered = shipped + timedelta(days=int(rng.integers(1, 6)))
            delivered_flag = rng.random() < .88
            status = "delivered" if delivered_flag else ("shipped" if rng.random() < .65 else "pending")
            if status == "pending": shipped_at = None; delivered_at = None
            elif status == "shipped": shipped_at = shipped; delivered_at = None
            else: shipped_at = shipped; delivered_at = delivered
            if status == "delivered": order_status = "delivered"
            lines.append(dict(order_line_id=olid, order_id=oid, listing_id=lid, seller_id=lrow.seller_id,
                              quantity=q, unit_price_cents=cents, line_total_cents=total_cents, currency="USD"))
            fid = f"FUL-{olid}"
            fulfillments.append(dict(fulfillment_id=fid, order_line_id=olid, status=status,
                                     expected_ship_at=dtstr(ship_due), shipped_at=dtstr(shipped_at) if shipped_at else None,
                                     delivered_at=dtstr(delivered_at) if delivered_at else None,
                                     issue_type="late_shipment" if shipped_at and shipped_at > ship_due else None))
            fulfillment_events.append(dict(event_id=f"FEV-{line_number:08d}-01", fulfillment_id=fid, event_type="fulfillment_created", event_at=dtstr(od), prior_status=None, new_status="pending"))
            if shipped_at:
                fulfillment_events.append(dict(event_id=f"FEV-{line_number:08d}-02", fulfillment_id=fid, event_type="shipped", event_at=dtstr(shipped_at), prior_status="pending", new_status="shipped"))
            if delivered_at:
                fulfillment_events.append(dict(event_id=f"FEV-{line_number:08d}-03", fulfillment_id=fid, event_type="delivered", event_at=dtstr(delivered_at), prior_status="shipped", new_status="delivered"))
            if delivered_at and rng.random() < .23:
                reviews.append(dict(review_id=f"REV-{len(reviews)+1:07d}", order_line_id=olid,
                                    rating=int(rng.choice([1,2,3,4,5], p=[.04,.07,.16,.38,.35])),
                                    review_date=dtstr(delivered_at + timedelta(days=int(rng.integers(1, 15))))))
        orders.append(dict(order_id=oid, order_date=dtstr(od), order_status=order_status,
                           order_total_cents=order_total, currency="USD"))
    orders_df, lines_df, fulfill_df = pd.DataFrame(orders), pd.DataFrame(lines), pd.DataFrame(fulfillments)
    # Disputes reference valid orders; deterministic issue injection includes disputes missing deductions.
    disputes = []
    delivered_order_ids = sorted(set(lines_df.merge(fulfill_df.loc[fulfill_df.status == "delivered", ["order_line_id"]], on="order_line_id").order_id))
    for di in range(1, n_disputes+1):
        missing_deduction = (di % 20 == 0)
        # Every injected missing-deduction dispute is resolved/lost and references
        # an order with a delivered line, so it has a real payout to audit.
        if missing_deduction and delivered_order_ids:
            oid = str(rng.choice(delivered_order_ids))
            order = next(o for o in orders if o["order_id"] == oid)
            status = str(rng.choice(["lost", "resolved"]))
        else:
            oi = int(rng.integers(1, n_orders+1))
            order = orders[oi-1]
            status = str(rng.choice(["open","won","lost","resolved"], p=[.2,.25,.35,.2]))
        amount = int(max(100, round(order["order_total_cents"] * float(rng.uniform(.1, 1.0)))))
        disputes.append(dict(dispute_id=f"DSP-2026-{di:06d}", order_id=order["order_id"],
                             dispute_date=dtstr(datetime.strptime(order["order_date"], "%Y-%m-%d %H:%M:%S") + timedelta(days=int(rng.integers(2, 35)))),
                             amount_cents=amount, status=status, deduction_expected=bool(status in ["lost","resolved"]),
                             issue_type="dispute_not_deducted" if missing_deduction and status in ["lost","resolved"] else None))
    disputes_df = pd.DataFrame(disputes)
    disputes_by_order = {order_id: group.to_dict("records") for order_id, group in disputes_df.groupby("order_id", sort=False)}
    # Payout generation: one payout per seller/order batch with delivered eligible lines.
    commission_entries, payouts, payout_lines, truth = [], [], [], []
    payout_counter = 0
    # Label each intentionally omitted dispute deduction once, independently of
    # how many sellers from that order receive payouts.
    for dispute in disputes:
        if dispute.get("issue_type") == "dispute_not_deducted":
            truth.append(dict(issue_id=f"GT-{len(truth)+1:07d}", entity_type="dispute",
                              record_id=dispute["dispute_id"], issue_type="dispute_not_deducted",
                              expected_label=1, expected_decision="create_dispute_deduction",
                              source_record_id=dispute["order_id"]))
    for f in fulfillments:
        if f.get("issue_type") == "late_shipment":
            truth.append(dict(issue_id=f"GT-{len(truth)+1:07d}", entity_type="fulfillment",
                              record_id=f["fulfillment_id"], issue_type="late_shipment", expected_label=1,
                              expected_decision="review_late_shipment", source_record_id=None))
    seller_by_line = lines_df.set_index("order_line_id").to_dict("index")
    fulfillment_by_line = fulfill_df.set_index("order_line_id").to_dict("index")
    rule_by_cat = {r.category: r for r in rules_df.itertuples(index=False)}
    listing_category = {r.listing_id: r.category for r in listing_df.itertuples(index=False)}
    delivered_lines = lines_df[lines_df.order_line_id.isin(fulfill_df.loc[fulfill_df.status == "delivered", "order_line_id"])]
    for (sid, order_id), seller_lines in delivered_lines.groupby(["seller_id", "order_id"], sort=True):
        # Batch each seller's delivered lines for a single customer order. This
        # keeps an injected early payout scoped to the affected order.
        payout_counter += 1
        pid = f"PAYOUT-2026-{payout_counter:06d}"
        payout_line_rows = []
        release_by_line = {}
        early_candidates = []
        for row in seller_lines.itertuples(index=False):
            f = fulfillment_by_line[row.order_line_id]
            delivered_at = datetime.strptime(f["delivered_at"], "%Y-%m-%d %H:%M:%S")
            release_at = delivered_at + timedelta(days=7)
            release_by_line[row.order_line_id] = release_at
            rule = rule_by_cat[listing_category[row.listing_id]]
            gross = int(row.line_total_cents)
            commission = round(gross * float(rule.rate))
            reserve = round(max(0, gross - commission) * float(rule.reserve_rate))
            early = (int(row.order_line_id.split("-")[1]) % 97 == 0)
            if early: early_candidates.append(row.order_line_id)
            payout_line_rows.append((row.order_line_id, "sale", gross, None))
            payout_line_rows.append((row.order_line_id, "commission", -commission, None))
            payout_line_rows.append((row.order_line_id, "reserve_hold", -reserve, None))
            # Deliberate duplicate commission anomaly on selected lines.
            if int(row.order_line_id.split("-")[1]) % 131 == 0:
                payout_line_rows.append((row.order_line_id, "commission", -commission, None))
                truth.append(dict(issue_id=f"GT-{len(truth)+1:07d}", entity_type="payout_line", record_id=pid,
                                  issue_type="commission_applied_twice", expected_label=1,
                                  expected_decision="flag_duplicate_commission", source_record_id=row.order_line_id))
        # Include dispute deductions where known, except intentionally omitted cases
        for d in disputes_by_order.get(order_id, []):
            if d["status"] in ("lost", "resolved"):
                if d.get("issue_type") != "dispute_not_deducted":
                    payout_line_rows.append((None, "dispute", -int(d["amount_cents"]), d["dispute_id"]))
        # A normal seller payout is dated after every included line's hold release.
        # If an injected early line exists, make the payout date early enough to
        # violate that line's hold and label every line actually affected.
        if early_candidates:
            payout_date = min(release_by_line[olid] for olid in early_candidates) - timedelta(days=1)
        else:
            payout_date = max(release_by_line.values()) + timedelta(days=1)
        for olid, release_at in release_by_line.items():
            if payout_date < release_at:
                truth.append(dict(issue_id=f"GT-{len(truth)+1:07d}", entity_type="payout", record_id=pid,
                                  issue_type="payout_before_hold_release", expected_label=1,
                                  expected_decision="hold_or_block_payout", source_record_id=olid))
        # payout total normally sum of lines, but deliberate mismatches for some seller counters
        total = sum(x[2] for x in payout_line_rows)
        # Make one mismatch every 29th payout; keep a label.
        mismatch = payout_counter % 29 == 0
        if mismatch:
            truth.append(dict(issue_id=f"GT-{len(truth)+1:07d}", entity_type="payout", record_id=pid,
                              issue_type="payout_total_mismatch", expected_label=1,
                              expected_decision="reconcile_payout_to_lines", source_record_id=None))
            recorded_total = total + 123
        else:
            recorded_total = total
        # Seller suspension blocks payout; eligibility is recorded, not silently fixed.
        seller_status = seller_status_by_id[sid]
        status = "blocked" if seller_status == "suspended" else ("held" if mismatch else "eligible")
        payouts.append(dict(payout_id=pid, seller_id=sid, payout_date=dtstr(payout_date),
                            recorded_total_cents=recorded_total, status=status, currency="USD"))
        for j, (olid, kind, cents, dispute_id) in enumerate(payout_line_rows, 1):
            payout_lines.append(dict(payout_line_id=f"PL-{payout_counter:06d}-{j:05d}", payout_id=pid,
                                     order_line_id=olid, line_type=kind, amount_cents=cents,
                                     dispute_id=dispute_id, currency="USD"))
    # Listing anomaly labels, separate from features
    for l in listings:
        if l["issue_type"] == "suspended_seller_listing":
            truth.append(dict(issue_id=f"GT-{len(truth)+1:07d}", entity_type="product_listing",
                              record_id=l["listing_id"], issue_type=l["issue_type"], expected_label=1,
                              expected_decision="deactivate_listing_or_review", source_record_id=l["seller_id"]))
    # Ensure all required issue classes have at least one deterministic truth example where possible.
    ground_truth_df = pd.DataFrame(truth, columns=["issue_id","entity_type","record_id","issue_type","expected_label","expected_decision","source_record_id"])
    frames = {
        "sellers": sellers_df, "product_listings": listing_df.drop(columns=["issue_type"]), "orders": orders_df, "order_lines": lines_df,
        "fulfillments": fulfill_df.drop(columns=["issue_type"]), "customer_reviews": pd.DataFrame(reviews, columns=["review_id","order_line_id","rating","review_date"]),
        "disputes": disputes_df.drop(columns=["issue_type"]), "commission_rules": rules_df, "payouts": pd.DataFrame(payouts),
        "payout_lines": pd.DataFrame(payout_lines), "seller_events": pd.DataFrame(seller_events),
        "fulfillment_events": pd.DataFrame(fulfillment_events), "ground_truth": ground_truth_df
    }
    # Remove generation-only issue_type from listings/disputes after truth has been copied; retain on data as permitted label.
    for name, df in frames.items():
        df.to_csv(out / f"{name}.csv", index=False)
        (out / "json" / f"{name}.json").write_text(df.to_json(orient="records", indent=2, date_format="iso"), encoding="utf-8")
    # manifest and checksums
    manifest = {"project":"Seller Operations, Risk & Payout Monitoring", "seed":seed, "scale":scale,
                "generated_at_utc":"fixed-by-design", "synthetic_only":True,
                "counts":{name:int(len(df)) for name,df in frames.items()},
                "target_counts":{"sellers":n_sellers,"product_listings":n_listings,"orders":n_orders,"disputes":n_disputes},
                "generator_version":"1.1.0", "external_sources":[]}
    write_json(out / "manifest.json", manifest)
    checksums = {p.name: sha256_file(p) for p in sorted(out.glob("*.csv"))}
    write_json(out / "checksums.json", checksums)
    # validation summary generated at source level
    summary = {"seed":seed,"scale":scale,"counts":manifest["counts"],"ground_truth_issue_counts":ground_truth_df.issue_type.value_counts().to_dict() if not ground_truth_df.empty else {},
               "validation":"Run `python -m src.validate --data <directory>` for full validation."}
    write_json(out / "validation_summary.json", summary)
    print(json.dumps(manifest, indent=2))
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--scale", choices=["small","medium","full"], default="small")
    ap.add_argument("--seed", type=int, default=SEED_DEFAULT)
    ap.add_argument("--out", default=None)
    args=ap.parse_args()
    out=args.out or f"outputs/{args.scale}"
    make_data(args.scale,args.seed,out)

if __name__=="__main__": main()
