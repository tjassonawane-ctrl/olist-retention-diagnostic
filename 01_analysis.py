"""
Customer Retention & Revenue Leakage Diagnostic - Olist E-commerce
SQL data model (DuckDB) + KPIs + diagnostics + revenue-at-risk sizing.

SETUP:      pip install duckdb pandas
FOLDER:     put the Olist CSV files in a folder called data/
RUN:        python 01_analysis.py
OUTPUT:     files in outputs/ (including the small files app.py reads)
"""
import os
import duckdb
import pandas as pd

DATA = "data"
OUT = "outputs"
os.makedirs(OUT, exist_ok=True)


def f(name):
    return os.path.join(DATA, name).replace("\\", "/")


con = duckdb.connect()

# ---------- 1. SQL DATA MODEL: one clean row per order ----------
SQL = f"""
WITH items AS (
    SELECT order_id,
           SUM(price)          AS item_revenue,
           SUM(freight_value)  AS freight_value,
           COUNT(*)            AS n_items,
           ANY_VALUE(product_id) AS product_id
    FROM read_csv_auto('{f("olist_order_items_dataset.csv")}')
    GROUP BY order_id
),
reviews AS (
    SELECT order_id, AVG(review_score) AS review_score
    FROM read_csv_auto('{f("olist_order_reviews_dataset.csv")}')
    GROUP BY order_id
),
pay AS (
    SELECT order_id, SUM(payment_value) AS payment_value
    FROM read_csv_auto('{f("olist_order_payments_dataset.csv")}')
    GROUP BY order_id
),
cat AS (
    SELECT p.product_id,
           COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category
    FROM read_csv_auto('{f("olist_products_dataset.csv")}') p
    LEFT JOIN read_csv_auto('{f("product_category_name_translation.csv")}') t
           ON p.product_category_name = t.product_category_name
)
SELECT
    o.order_id,
    c.customer_unique_id,
    c.customer_state,
    o.order_status,
    CAST(o.order_purchase_timestamp AS TIMESTAMP)          AS purchase_ts,
    CAST(o.order_delivered_customer_date AS TIMESTAMP)     AS delivered_ts,
    CAST(o.order_estimated_delivery_date AS TIMESTAMP)     AS estimated_ts,
    i.item_revenue,
    i.freight_value,
    i.n_items,
    COALESCE(pay.payment_value, i.item_revenue + i.freight_value) AS order_value,
    r.review_score,
    COALESCE(cat.category, 'unknown')                      AS category
FROM read_csv_auto('{f("olist_orders_dataset.csv")}') o
JOIN read_csv_auto('{f("olist_customers_dataset.csv")}') c ON o.customer_id = c.customer_id
LEFT JOIN items   i   ON o.order_id = i.order_id
LEFT JOIN reviews r   ON o.order_id = r.order_id
LEFT JOIN pay         ON o.order_id = pay.order_id
LEFT JOIN cat         ON i.product_id = cat.product_id
"""
df = con.execute(SQL).df()

df = df[df["order_status"] == "delivered"].dropna(subset=["delivered_ts", "order_value"]).copy()
df["delivery_days"] = (df["delivered_ts"] - df["purchase_ts"]).dt.total_seconds() / 86400
df["days_late"] = (df["delivered_ts"] - df["estimated_ts"]).dt.total_seconds() / 86400
df["is_late"] = (df["days_late"] > 0).astype(int)
df["month"] = df["purchase_ts"].dt.to_period("M").astype(str)
df.to_csv(f"{OUT}/orders_master.csv", index=False)

# ---------- 2. HEADLINE KPIs ----------
total_rev = df["order_value"].sum()
n_orders = len(df)
n_customers = df["customer_unique_id"].nunique()
aov = df["order_value"].mean()
late_rate = df["is_late"].mean()
avg_review = df["review_score"].mean()

# ---------- 3. CUSTOMER LEVEL: repeat behaviour ----------
df = df.sort_values(["customer_unique_id", "purchase_ts"])
df["order_rank"] = df.groupby("customer_unique_id").cumcount() + 1

cust = df.groupby("customer_unique_id").agg(
    orders=("order_id", "count"),
    revenue=("order_value", "sum"),
    first_purchase=("purchase_ts", "min"),
    last_purchase=("purchase_ts", "max"),
    state=("customer_state", "first"),
).reset_index()
cust["is_repeat"] = (cust["orders"] > 1).astype(int)
repeat_rate = cust["is_repeat"].mean()

first = df[df["order_rank"] == 1][["customer_unique_id", "is_late", "review_score", "order_value"]]
first = first.rename(columns={"is_late": "first_late", "review_score": "first_review",
                              "order_value": "first_order_value"})
cust = cust.merge(first, on="customer_unique_id", how="left")

# ---------- 4. DIAGNOSTIC: does a bad delivery kill repeat purchase? ----------
rev_by_late = df.groupby("is_late")["review_score"].mean()
rep_by_first_late = cust.groupby("first_late")["is_repeat"].mean()

n_late_first = int((cust["first_late"] == 1).sum())
gap = rep_by_first_late.get(0, 0) - rep_by_first_late.get(1, 0)
extra_repeat_customers = n_late_first * max(gap, 0)
avg_repeat_order_value = df[df["order_rank"] > 1]["order_value"].mean()
if pd.isna(avg_repeat_order_value):
    avg_repeat_order_value = aov
revenue_at_risk = extra_repeat_customers * avg_repeat_order_value

state_perf = df.groupby("customer_state").agg(
    orders=("order_id", "count"),
    late_rate=("is_late", "mean"),
    avg_review=("review_score", "mean"),
    revenue=("order_value", "sum"),
).sort_values("late_rate", ascending=False)
state_perf = state_perf[state_perf["orders"] >= max(50, int(0.005 * n_orders))]

# ---------- 5. COHORT RETENTION (monthly) ----------
cust["cohort"] = cust["first_purchase"].dt.to_period("M")
tmp = df.merge(cust[["customer_unique_id", "cohort"]], on="customer_unique_id")
tmp["period"] = tmp["purchase_ts"].dt.to_period("M")
tmp["month_index"] = (tmp["period"] - tmp["cohort"]).apply(lambda x: x.n)
cohort = (tmp.groupby(["cohort", "month_index"])["customer_unique_id"]
          .nunique().unstack(fill_value=0))
cohort_pct = cohort.div(cohort[0], axis=0).round(4)
cohort_pct.to_csv(f"{OUT}/cohort_retention.csv")

# ---------- 6. RFM SEGMENTATION ----------
snapshot = df["purchase_ts"].max() + pd.Timedelta(days=1)
cust["recency"] = (snapshot - cust["last_purchase"]).dt.days
cust["R"] = pd.qcut(-cust["recency"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)
cust["M"] = pd.qcut(cust["revenue"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)


def segment(r):
    if r["orders"] > 1 and r["M"] >= 3:
        return "Loyal high-value"
    if r["orders"] > 1:
        return "Loyal"
    if r["M"] == 4 and r["R"] >= 3:
        return "New high-value (nurture)"
    if r["M"] == 4:
        return "Lapsed high-value (win-back)"
    return "One-time low/mid value"


cust["segment"] = cust.apply(segment, axis=1)
seg = cust.groupby("segment").agg(customers=("customer_unique_id", "count"),
                                  revenue=("revenue", "sum")).sort_values("revenue", ascending=False)
seg["revenue_share_%"] = (seg["revenue"] / seg["revenue"].sum() * 100).round(1)
seg.to_csv(f"{OUT}/rfm_segments.csv")
cust.to_csv(f"{OUT}/customers.csv", index=False)

# ---------- 7. PRINT THE INSIGHTS ----------
print("\n================ KEY NUMBERS ================")
print(f"Delivered orders        : {n_orders:,}")
print(f"Unique customers        : {n_customers:,}")
print(f"Total revenue           : {total_rev:,.0f}")
print(f"Average order value     : {aov:,.2f}")
print(f"Late-delivery rate      : {late_rate*100:.1f}%")
print(f"Average review score    : {avg_review:.2f}")
print(f"Repeat-customer rate    : {repeat_rate*100:.1f}%   -> never reorder = {100-repeat_rate*100:.1f}%")
print("\nReview score  on-time vs late:")
print(rev_by_late.round(2).rename({0: "on-time", 1: "late"}).to_string())
print("\nRepeat rate (%) by whether FIRST order was late:")
print((rep_by_first_late * 100).round(2).rename({0: "on-time", 1: "late"}).to_string())
print(f"\nCustomers whose first order was late : {n_late_first:,}")
print(f"Repeat-rate gap (on-time minus late) : {gap*100:.2f} percentage points")
print(f"Estimated revenue at risk            : {revenue_at_risk:,.0f}")
print("\nTop 5 states by late-delivery rate:")
print(state_perf.head(5).round(3).to_string())
print("\nTop 5 categories by revenue:")
print(df.groupby("category")["order_value"].sum().sort_values(ascending=False).head(5).round(0).to_string())
print("\nRFM segments:")
print(seg.round(1).to_string())
print("\nSaved files in ./outputs/")

# ---------- 8. SMALL COMPRESSED FILES FOR THE STREAMLIT DASHBOARD (app.py) ----------
cols = ["order_id", "customer_unique_id", "customer_state", "purchase_ts",
        "order_value", "review_score", "category", "is_late", "month"]
df[cols].to_csv(f"{OUT}/orders_slim.csv.gz", index=False, compression="gzip")
cust[["customer_unique_id", "revenue", "is_repeat", "first_late", "segment"]].to_csv(
    f"{OUT}/customers_slim.csv.gz", index=False, compression="gzip")
