import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Olist Retention Diagnostic", layout="wide")


@st.cache_data
def load():
    o = pd.read_csv(
        "outputs/orders_slim.csv.gz",
        parse_dates=["purchase_ts"],
        usecols=["order_id", "customer_unique_id", "customer_state", "purchase_ts",
                 "order_value", "review_score", "category", "is_late", "month"],
    )
    c = pd.read_csv("outputs/customers_slim.csv.gz")
    coh = pd.read_csv("outputs/cohort_retention.csv", index_col=0)
    return o, c, coh


orders, cust, cohort = load()
orders["total_orders"] = orders.groupby("customer_unique_id")["order_id"].transform("nunique")

# ---------------- Sidebar filters ----------------
st.sidebar.header("Filters")
min_d, max_d = orders["purchase_ts"].min().date(), orders["purchase_ts"].max().date()
date_range = st.sidebar.date_input("Purchase date range", (min_d, max_d), min_value=min_d, max_value=max_d)
states = sorted(orders["customer_state"].dropna().unique())
sel_states = st.sidebar.multiselect("State", states, default=states)
cats = sorted(orders["category"].dropna().unique())
sel_cats = st.sidebar.multiselect("Category (leave empty = all)", cats, default=[])

df = orders[orders["customer_state"].isin(sel_states)]
if len(date_range) == 2:
    df = df[(df["purchase_ts"].dt.date >= date_range[0]) & (df["purchase_ts"].dt.date <= date_range[1])]
if sel_cats:
    df = df[df["category"].isin(sel_cats)]

# ---------------- Header ----------------
st.title("Why 97% of customers never come back")
st.caption("Customer retention & revenue diagnostic | Olist Brazilian e-commerce data | Currency: R$ (BRL)")

if df.empty:
    st.warning("No data for these filters.")
    st.stop()

# ---------------- KPI cards ----------------
repeat_rate = (df.drop_duplicates("customer_unique_id")["total_orders"] > 1).mean()
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Revenue", f"R$ {df['order_value'].sum()/1e6:.2f}M")
k2.metric("Orders", f"{len(df):,}")
k3.metric("Avg order value", f"R$ {df['order_value'].mean():.0f}")
k4.metric("Late deliveries", f"{df['is_late'].mean()*100:.1f}%")
k5.metric("Avg review", f"{df['review_score'].mean():.2f}")
k6.metric("Repeat customers", f"{repeat_rate*100:.1f}%")

tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Delivery vs loyalty", "Retention & segments", "Opportunity sizer"])

# ---------------- Tab 1: Overview ----------------
with tab1:
    c1, c2 = st.columns(2)
    monthly = df.groupby("month")["order_value"].sum().reset_index()
    c1.plotly_chart(px.line(monthly, x="month", y="order_value", markers=True,
                            title="Monthly revenue (R$)"), width="stretch")
    top_cat = (df.groupby("category")["order_value"].sum().sort_values(ascending=False)
               .head(10).reset_index())
    c2.plotly_chart(px.bar(top_cat, x="order_value", y="category", orientation="h",
                           title="Top 10 categories by revenue (R$)")
                    .update_yaxes(autorange="reversed"), width="stretch")

# ---------------- Tab 2: Delivery vs loyalty ----------------
with tab2:
    st.markdown("**Late delivery wrecks reviews, but only slightly reduces repeat purchase.**")
    c1, c2 = st.columns(2)
    rv = df.groupby("is_late")["review_score"].mean().rename({0: "On-time", 1: "Late"}).reset_index()
    rv.columns = ["Delivery", "Avg review"]
    c1.plotly_chart(px.bar(rv, x="Delivery", y="Avg review", text_auto=".2f",
                           title="Review score: on-time vs late"), width="stretch")
    rp = (cust.groupby("first_late")["is_repeat"].mean() * 100).rename({0: "On-time", 1: "Late"}).reset_index()
    rp.columns = ["First order", "Repeat rate %"]
    c2.plotly_chart(px.bar(rp, x="First order", y="Repeat rate %", text_auto=".2f",
                           title="Repeat rate by first-order delivery (%)"), width="stretch")

    st_perf = df.groupby("customer_state").agg(orders=("order_id", "count"),
                                               late_rate=("is_late", "mean"),
                                               revenue=("order_value", "sum")).reset_index()
    st_perf = st_perf[st_perf["orders"] >= 100].sort_values("late_rate", ascending=False)
    st_perf["late_rate"] = st_perf["late_rate"] * 100
    st.plotly_chart(px.bar(st_perf, x="customer_state", y="late_rate", color="revenue",
                           title="Late-delivery rate by state (%), colour = revenue"),
                    width="stretch")

# ---------------- Tab 3: Retention & segments ----------------
with tab3:
    seg = cust.groupby("segment").agg(customers=("customer_unique_id", "count"),
                                      revenue=("revenue", "sum")).reset_index()
    seg["Revenue share %"] = seg["revenue"] / seg["revenue"].sum() * 100
    one_time = seg[~seg["segment"].str.startswith("Loyal")]["Revenue share %"].sum()
    st.markdown(f"**About {one_time:.0f}% of revenue comes from customers who bought only once.**")
    c1, c2 = st.columns(2)
    c1.plotly_chart(px.bar(seg.sort_values("Revenue share %"), x="Revenue share %", y="segment",
                           orientation="h", title="Revenue share by customer segment"),
                    width="stretch")
    c2.plotly_chart(px.bar(seg.sort_values("customers"), x="customers", y="segment",
                           orientation="h", title="Customers by segment"), width="stretch")

    coh = cohort.copy()
    coh.index = pd.PeriodIndex(coh.index, freq="M")
    coh.columns = coh.columns.astype(int)
    last = coh.index.max()
    coh = coh[coh.index >= pd.Period("2017-01", freq="M")]
    for cidx in coh.index:                       # hide months that have not happened yet
        elapsed = (last - cidx).n
        coh.loc[cidx, [m for m in coh.columns if m > elapsed]] = float("nan")
    coh = coh[[m for m in coh.columns if 1 <= m <= 6]] * 100
    coh.index = coh.index.astype(str)
    st.plotly_chart(px.imshow(coh, text_auto=".1f", aspect="auto", color_continuous_scale="Blues",
                              labels=dict(x="Months since first order", y="First-order month", color="% returned"),
                              title="Cohort retention: % of customers who ordered again"),
                    width="stretch")

# ---------------- Tab 4: Opportunity sizer ----------------
with tab4:
    st.subheader("What if we convert first-time high-value customers into repeat buyers?")
    hv = cust[cust["segment"].isin(["New high-value (nurture)", "Lapsed high-value (win-back)"])]
    n_hv, avg_hv = len(hv), hv["revenue"].mean()
    total_rev = cust["revenue"].sum()
    s1, s2 = st.columns(2)
    conv = s1.slider("% of these customers converted to a 2nd order", 1, 20, 5)
    val = s2.slider("2nd-order value as % of their first order", 25, 100, 100)
    uplift = n_hv * conv / 100 * avg_hv * val / 100
    m1, m2, m3 = st.columns(3)
    m1.metric("Target customers", f"{n_hv:,}")
    m2.metric("Extra revenue", f"R$ {uplift:,.0f}")
    m3.metric("As % of current revenue", f"{uplift/total_rev*100:.1f}%")
    st.caption("Illustrative scenario, not a forecast. Target group = new + lapsed high-value one-time buyers; each converted customer places one extra order at the chosen value.")
