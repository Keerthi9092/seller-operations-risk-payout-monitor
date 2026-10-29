import json
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Seller Ops Monitor", page_icon="📦", layout="wide")
st.title("Seller Operations, Risk & Payout Monitor")
st.caption("Synthetic challenge dataset • seller health • fulfillment • financial exceptions")
data_dir=st.sidebar.text_input("Dataset directory","outputs/small")
d=Path(data_dir)
if not d.exists() or not (d/"sellers.csv").exists():
    st.warning("Dataset not found. Run: python -m src.generate --scale small --seed 20261022 --out outputs/small")
    st.stop()
def read(n):
    p=d/f"{n}.csv"
    return pd.read_csv(p, keep_default_na=False) if p.exists() else pd.DataFrame()
sellers=read("sellers"); listings=read("product_listings"); orders=read("orders"); lines=read("order_lines")
ful=read("fulfillments"); disputes=read("disputes"); payouts=read("payouts"); pl=read("payout_lines")
gt=read("ground_truth"); findings=read("detected_anomalies")
c1,c2,c3,c4=st.columns(4)
c1.metric("Sellers",f"{len(sellers):,}")
c2.metric("Orders",f"{len(orders):,}")
c3.metric("Disputes",f"{len(disputes):,}")
c4.metric("Payouts",f"{len(payouts):,}")
tab1,tab2,tab3,tab4=st.tabs(["Seller health","Fulfillment","Payouts","Exceptions"])
with tab1:
    counts=sellers.status.value_counts().rename_axis("status").reset_index(name="sellers")
    st.plotly_chart(px.bar(counts,x="status",y="sellers",title="Seller lifecycle status"),use_container_width=True)
    if len(lines):
        performance=lines.groupby("seller_id").order_id.nunique().rename("orders").reset_index()
        performance=performance.merge(sellers[["seller_id","status"]],on="seller_id",how="left")
        st.subheader("Seller order volume")
        st.dataframe(performance.sort_values("orders",ascending=False).head(25),use_container_width=True)
with tab2:
    if len(ful):
        fc=ful.status.value_counts().rename_axis("fulfillment_status").reset_index(name="count")
        st.plotly_chart(px.pie(fc,names="fulfillment_status",values="count",title="Fulfillment status mix"),use_container_width=True)
        late=ful[(ful.shipped_at!="")&(ful.shipped_at>ful.expected_ship_at)]
        st.metric("Late shipments",f"{len(late):,}")
        st.dataframe(late.head(100),use_container_width=True)
with tab3:
    if len(payouts):
        line_sums=pl.assign(amount_cents=pd.to_numeric(pl.amount_cents)).groupby("payout_id").amount_cents.sum().rename("line_sum_cents")
        rec=payouts.copy(); rec["recorded_total_cents"]=pd.to_numeric(rec.recorded_total_cents)
        rec=rec.join(line_sums,on="payout_id")
        rec["line_sum_cents"]=rec.line_sum_cents.fillna(0)
        rec["reconciles"]=rec.recorded_total_cents==rec.line_sum_cents
        st.metric("Payouts reconciling",f"{int(rec.reconciles.sum()):,} / {len(rec):,}")
        st.dataframe(rec[~rec.reconciles].head(100),use_container_width=True)
        st.subheader("Payout status")
        st.plotly_chart(px.histogram(payouts,x="status",title="Payout lifecycle"),use_container_width=True)
with tab4:
    if findings.empty and (d/"detected_anomalies.csv").exists():
        findings=read("detected_anomalies")
    st.metric("Ground-truth anomaly labels",f"{len(gt):,}")
    st.metric("Detected findings",f"{len(findings):,}")
    if len(findings):
        st.plotly_chart(px.histogram(findings,x="issue_type",title="Detected issue types"),use_container_width=True)
        st.dataframe(findings,use_container_width=True)
    report=d/"evaluation_report.json"
    if report.exists():
        st.subheader("Evaluation")
        st.json(json.loads(report.read_text(encoding="utf-8")))
st.caption("Synthetic data only. Review business policy and accounting assumptions before real-world use.")
