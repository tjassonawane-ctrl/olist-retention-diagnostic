# Why 97% of Customers Never Come Back

Customer retention and revenue diagnostic of a Brazilian e-commerce marketplace (Olist), built with SQL, Python and Streamlit.

**Live dashboard:** https://olist-retention.streamlit.app

## Business question
Most customers buy once and never return. Where is the business losing value, and is delivery performance the cause?

## Key findings
- **97% of customers never reorder.** Only 3.0% of 93,350 customers placed a second order.
- **About 94% of revenue comes from one-time buyers.** Repeat customers contribute only about 6%.
- **Late delivery hurts reviews, but barely changes repeat buying.** Late orders average a 2.57 review vs 4.29 for on-time orders, but customers whose first order was late reorder at 2.49% vs 3.05% (a 0.56 percentage point gap).
- **So delivery is not the main retention lever.** Estimated revenue at risk from late first deliveries is only about R$ 6k, against R$ 15.4M total revenue.
- **The opportunity is the second purchase.** 21,567 high-value customers (new plus lapsed) bought once, averaging about R$ 391 each.
- **Delivery problems are concentrated by region.** MA (19.7%), CE (15.3%), BA (14.0%) and RJ (13.5%) have the highest late rates; RJ also carries R$ 2.06M of revenue.

## Recommendations
1. **Launch a second-purchase programme** for high-value one-time customers (post-purchase offers, win-back messages). Illustrative scenario: converting 5% of them to one extra order is worth about R$ 421k, roughly 2.7% of revenue.
2. **Fix delivery for reputation, not retention.** Prioritise high-revenue, high-delay states (RJ, BA) to protect review scores.
3. **Test before scaling.** Run an A/B test on retention offers and track repeat rate monthly in the dashboard.

## Dashboard
Four tabs: Overview (KPIs, revenue trend, top categories), Delivery vs loyalty, Retention and segments (cohort heatmap, RFM-style segments), and an Opportunity sizer with adjustable assumptions. Filters for date, state and category.

## Method
1. Joined 6 Olist tables with SQL (DuckDB) into one order-level table.
2. Kept delivered orders; calculated delivery delay vs estimated date.
3. Built customer-level repeat behaviour, monthly cohort retention and RFM-style segments.
4. Sized the opportunity with a simple scenario model.

## Limitations
- The data covers roughly 2016-2018, so recent customers have had little time to reorder, which pushes the repeat rate down.
- Olist is a marketplace with many one-off purchases, so a low repeat rate is partly structural.
- The findings show association, not causation. The R$ 421k figure is an assumption-based scenario, not a forecast.
- Revenue is in Brazilian reais (R$).

## Files
- `01_analysis.py`: SQL data model, KPIs and diagnostics
- `app.py`: Streamlit dashboard
- `outputs/`: processed data used by the dashboard

Data: Olist Brazilian E-Commerce Public Dataset (Kaggle).
