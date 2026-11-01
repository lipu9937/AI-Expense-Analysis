import json
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from core import analytics as an
from core import db, importer, llm, reports

st.set_page_config(page_title="AI Expense Analyzer", page_icon="💸", layout="wide")
db.init_db()

st.markdown("""<style>
[data-testid="stMetric"]{background:rgba(120,130,150,.10);padding:14px 16px;border-radius:12px}
.block-container{padding-top:2rem}
</style>""", unsafe_allow_html=True)

PAYMENTS = ["UPI", "Credit Card", "Debit Card", "Cash", "Net Banking", "Other"]
PAGES = ["📊 Dashboard", "🧾 Expenses", "🤖 AI Analysis", "💬 Assistant",
         "🎯 Budgets & Savings", "📄 Reports"]
fmt = lambda x: f"₹{x:,.0f}"

INSIGHT_PROMPT = ("Write personalized financial insights from DATA with these sections: "
                  "1) Summary 2) Biggest spending areas 3) Month-over-month changes "
                  "4) Unnecessary or repeated expenses 5) Unusual transactions 6) Five practical actions. "
                  "Quote numbers exactly as they appear in DATA.")
CHAT_PROMPT = ("Answer the user's question using DATA only. 'This month' means current_month. "
               "If DATA cannot answer it, say so plainly.")

page = st.sidebar.radio("Navigation", PAGES, label_visibility="collapsed")
st.sidebar.divider()
provider_name = llm.get_provider() if hasattr(llm, "get_provider") else llm.PROVIDER
st.sidebar.caption(f"LLM: **{provider_name}** · " +
                   ("connected ✅" if llm.available() else "no API key ⚠️ (keyword fallback only)"))

df, budgets, income = db.load_df(), db.get_budgets(), db.get_income()


def need_data():
    if df.empty:
        st.info("No expenses yet. Add one or import a bank statement on the **Expenses** page.")
        st.stop()


# ───────────────────────── Dashboard ─────────────────────────
if page == PAGES[0]:
    st.title("📊 Dashboard")
    need_data()
    months = sorted(df["month"].unique(), reverse=True)
    sel = st.selectbox("Period", ["All time"] + months)
    d = df if sel == "All time" else df[df["month"] == sel]
    total = float(d["amount"].sum())
    days = max((d["date"].max() - d["date"].min()).days + 1, 1)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total expenses", fmt(total))
    if income:
        c2.metric("Savings", fmt(income * d["month"].nunique() - total))
    else:
        c2.metric("Savings", "Set income →")
    c3.metric("Transactions", len(d))
    c4.metric("Avg per day", fmt(total / days))

    a, b = st.columns(2)
    cat = d.groupby("category", as_index=False)["amount"].sum()
    a.plotly_chart(px.pie(cat, names="category", values="amount", hole=.45,
                          title="Spending by category"), width="stretch")
    mon = df.groupby("month", as_index=False)["amount"].sum()
    b.plotly_chart(px.bar(mon, x="month", y="amount", title="Monthly expenses", text_auto=".2s"),
                   width="stretch")
    daily = d.groupby(d["date"].dt.date, as_index=False)["amount"].sum()
    st.plotly_chart(px.line(daily, x="date", y="amount", markers=True, title="Daily expenses"),
                    width="stretch")
    cm = df.groupby(["month", "category"], as_index=False)["amount"].sum()
    st.plotly_chart(px.bar(cm, x="month", y="amount", color="category", barmode="stack",
                           title="Category-wise comparison by month"), width="stretch")

# ───────────────────────── Expenses ─────────────────────────
elif page == PAGES[1]:
    st.title("🧾 Expenses")
    tab_add, tab_imp, tab_manage = st.tabs(["➕ Add Expense", "📥 Import Statement", "✏️ Manage"])

    with tab_add:
        with st.form("add", clear_on_submit=True):
            c1, c2 = st.columns(2)
            amount = c1.number_input("Amount (₹)", min_value=0.0, step=10.0, format="%.2f")
            when = c2.date_input("Date", value=date.today())
            desc = st.text_input("Description", placeholder="e.g. Swiggy dinner")
            c3, c4 = st.columns(2)
            pay = c3.selectbox("Payment method", PAYMENTS)
            cat_choice = c4.selectbox("Category", ["Auto (AI)"] + llm.CATEGORIES)
            ok = st.form_submit_button("Add expense", type="primary")
        if ok:
            if amount <= 0:
                st.error("Amount must be greater than zero.")
            elif not desc.strip():
                st.error("Please enter a description.")
            else:
                cat = cat_choice
                if cat_choice == "Auto (AI)":
                    cat = llm.categorize([desc])[0][desc.strip()]
                db.insert_many([{"date": when.isoformat(), "description": desc.strip(), "amount": amount,
                                 "category": cat, "payment_method": pay}], manual=True)
                st.success(f"Added ₹{amount:,.2f} under **{cat}**.")
                st.rerun()

    with tab_imp:
        st.caption("Upload a CSV or Excel bank statement. Only debit/expense rows are imported. "
                   "Re-uploading the same file will not create duplicates.")
        up = st.file_uploader("Bank statement", type=["csv", "xlsx", "xls"])
        if up:
            try:
                raw = importer.read_file(up)
                guess = importer.detect_columns(raw.columns)
                st.write("Preview", raw.head(5))
                opts = ["—"] + list(raw.columns)
                pick = lambda k: opts.index(guess[k]) if k in guess else 0
                c1, c2, c3, c4 = st.columns(4)
                mapping = {"date": c1.selectbox("Date column", opts, pick("date")),
                           "description": c2.selectbox("Description column", opts, pick("description")),
                           "debit": c3.selectbox("Debit/Withdrawal column", opts, pick("debit")),
                           "amount": c4.selectbox("…or single Amount column", opts, pick("amount"))}
                mapping = {k: (None if v == "—" else v) for k, v in mapping.items()}
                pay = st.selectbox("Payment method for these rows", PAYMENTS, index=PAYMENTS.index("Net Banking"))
                if st.button("Categorize and import", type="primary"):
                    tx = importer.normalize(raw, mapping)
                    if tx.empty:
                        st.warning("No valid expense rows were found with these column choices.")
                    else:
                        with st.spinner(f"Categorizing {tx['description'].nunique()} unique descriptions…"):
                            cmap, used = llm.categorize(tx["description"].tolist())
                        rows = [{"date": r.date.strftime("%Y-%m-%d"), "description": r.description,
                                 "amount": r.amount, "seq": r.seq, "payment_method": pay,
                                 "category": cmap[r.description.strip()]} for r in tx.itertuples()]
                        added, skipped = db.insert_many(rows)
                        st.success(f"Imported {added} transactions. Skipped {skipped} duplicates.")
                        if not used:
                            st.warning("LLM unavailable: keyword rules were used. You can fix categories in Manage.")
                        st.rerun()
            except Exception as e:
                st.error(f"Could not process the file: {e}")

    with tab_manage:
        if df.empty:
            st.info("Nothing to manage yet.")
        else:
            view = df[["id", "date", "description", "amount", "category", "payment_method"]].copy()
            view["date"] = view["date"].dt.date
            view["delete"] = False
            edited = st.data_editor(
                view, hide_index=True, width="stretch", disabled=["id"], key="editor",
                column_config={
                    "date": st.column_config.DateColumn("Date"),
                    "amount": st.column_config.NumberColumn("Amount (₹)", min_value=0.01, format="%.2f"),
                    "category": st.column_config.SelectboxColumn(options=llm.CATEGORIES),
                    "payment_method": st.column_config.SelectboxColumn(options=PAYMENTS)})
            if st.button("Save changes", type="primary"):
                upd = dele = 0
                for (_, o), (_, e) in zip(view.iterrows(), edited.iterrows()):
                    if e["delete"]:
                        db.delete_expense(e["id"]); dele += 1
                    elif any(str(o[c]) != str(e[c]) for c in view.columns if c != "delete"):
                        if not str(e["description"]).strip() or not e["amount"] or e["amount"] <= 0:
                            st.error(f"Row {e['id']}: invalid description or amount, skipped.")
                            continue
                        db.update_expense(e["id"], e["date"], e["description"], e["amount"],
                                          e["category"], e["payment_method"]); upd += 1
                st.success(f"Updated {upd}, deleted {dele}.")
                st.rerun()

# ───────────────────────── AI Analysis ─────────────────────────
elif page == PAGES[2]:
    st.title("🤖 AI Expense Analysis")
    need_data()
    ctx = an.build_context(df, budgets, income)
    if st.button("✨ Generate AI insights", type="primary"):
        try:
            with st.spinner("Analyzing your spending…"):
                st.session_state["insights"] = llm.ask(
                    llm.GUARD + INSIGHT_PROMPT, "DATA:\n" + json.dumps(ctx))
        except llm.LLMError as e:
            st.error(str(e))
    if "insights" in st.session_state:
        st.markdown(st.session_state["insights"])

    st.subheader("Computed facts (from your records)")
    ch = an.category_change(df)
    with st.expander(f"Category change: previous vs latest month", expanded=True):
        if ch.empty:
            st.info("Need at least two months of data to compare.")
        else:
            st.dataframe(ch, hide_index=True, width="stretch")
    with st.expander("Repeated expenses"):
        st.dataframe(an.repeated(df), hide_index=True, width="stretch")
    with st.expander("Unusual transactions"):
        an_df = an.anomalies(df)
        st.dataframe(an_df, hide_index=True, width="stretch") if len(an_df) else st.write("None detected.")

# ───────────────────────── Assistant ─────────────────────────
elif page == PAGES[3]:
    st.title("💬 AI Financial Assistant")
    need_data()
    st.caption("Try: *Where am I spending the most?* · *How much did I spend on food this month?* · "
               "*How can I save ₹5,000 next month?* · *Which category increased the most?*")
    st.session_state.setdefault("chat", [])
    for m in st.session_state["chat"]:
        st.chat_message(m["role"]).write(m["content"])
    if q := st.chat_input("Ask about your spending…"):
        st.chat_message("user").write(q)
        data = json.dumps(an.build_context(df, budgets, income))
        try:
            with st.spinner("Thinking…"):
                ans = llm.ask(llm.GUARD + CHAT_PROMPT, f"DATA:\n{data}\n\nQUESTION: {q}",
                              history=st.session_state["chat"][-6:])
        except llm.LLMError as e:
            ans = f"⚠️ {e}"
        st.chat_message("assistant").write(ans)
        st.session_state["chat"] += [{"role": "user", "content": q}, {"role": "assistant", "content": ans}]
    if st.session_state["chat"] and st.sidebar.button("Clear chat"):
        st.session_state["chat"] = []
        st.rerun()

# ───────────────────────── Budgets & Savings ─────────────────────────
elif page == PAGES[4]:
    st.title("🎯 Budgets & Savings")
    inc = st.number_input("Monthly income (₹)", min_value=0.0, value=float(income), step=1000.0)
    if st.button("Save income"):
        db.set_income(inc)
        st.success("Income saved. Reload the page to refresh savings figures.")
        st.rerun()

    st.subheader("Monthly budgets")
    b = pd.DataFrame({"Category": llm.CATEGORIES,
                      "Monthly budget": [float(budgets.get(c, 0.0)) for c in llm.CATEGORIES]})
    eb = st.data_editor(b, hide_index=True, disabled=["Category"], width="stretch",
                        column_config={"Monthly budget": st.column_config.NumberColumn(min_value=0.0, step=100.0)})
    if st.button("Save budgets", type="primary"):
        db.set_budgets({r["Category"]: r["Monthly budget"] for _, r in eb.iterrows()})
        st.success("Budgets saved.")
        st.rerun()

    if not df.empty:
        st.subheader("Recommended budgets & forecast")
        rec = an.recommended_budgets(df)
        st.caption("Based on your last 3 months; flexible categories are trimmed by 10%.")
        st.dataframe(pd.DataFrame({"Category": list(rec.keys()), "Recommended (₹)": list(rec.values())}),
                     hide_index=True, width="stretch")
        if st.button("Apply recommended budgets"):
            db.set_budgets(rec)
            st.success("Applied. Reload to see them above.")
            st.rerun()
        fc = an.forecast(df)
        st.metric("Predicted next-month spending", fmt(fc["next_month_total"]), help=fc["method"])
        fdf = pd.DataFrame({"category": list(fc["category_avg_last_3_months"].keys()),
                            "amount": list(fc["category_avg_last_3_months"].values())})
        st.plotly_chart(px.bar(fdf, x="category", y="amount",
                               title="Average monthly spend per category (last 3 months)"), width="stretch")

        st.subheader("Savings plan")
        target = st.number_input("Amount I want to save next month (₹)", min_value=0.0, value=5000.0, step=500.0)
        if st.button("Create savings plan", type="primary"):
            ctx = an.build_context(df, budgets, income,
                                   extra={"saving_target": target, "flexible_categories": an.FLEX})
            try:
                with st.spinner("Building your plan…"):
                    st.markdown(llm.ask(
                        llm.GUARD + "Create a practical plan to save saving_target next month. Cut mainly from "
                        "flexible_categories using category_avg_last_3_months, show the arithmetic with numbers "
                        "from DATA, and list specific habits.", "DATA:\n" + json.dumps(ctx)))
            except llm.LLMError as e:
                st.error(str(e))

# ───────────────────────── Reports ─────────────────────────
else:
    st.title("📄 Monthly Reports")
    need_data()
    month = st.selectbox("Month", sorted(df["month"].unique(), reverse=True))
    rep = reports.build(df, budgets, income, month)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total spent", fmt(rep["total"]))
    c2.metric("Savings", fmt(rep["savings"]) if rep["savings"] is not None else "Set income")
    c3.metric("Transactions", rep["count"])

    a, b = st.columns(2)
    a.plotly_chart(px.bar(rep["categories"], x="Category", y="Spent", title="Highest spending categories"),
                   width="stretch")
    bt = rep["budget_table"]
    bt_long = bt[bt["Budget"] > 0].melt(id_vars="Category", value_vars=["Spent", "Budget"])
    if len(bt_long):
        b.plotly_chart(px.bar(bt_long, x="Category", y="value", color="variable", barmode="group",
                              title="Budget vs actual"), width="stretch")
    else:
        b.info("Set budgets to see a budget comparison.")
    st.dataframe(rep["categories"], hide_index=True, width="stretch")
    st.dataframe(bt, hide_index=True, width="stretch")

    narrative = ""
    if st.button("Add AI summary to report"):
        ctx = an.build_context(df[df["month"] <= month], budgets, income)
        try:
            with st.spinner("Writing summary…"):
                st.session_state[f"narr_{month}"] = llm.ask(
                    llm.GUARD + f"Write a short monthly financial summary for {month}.",
                    "DATA:\n" + json.dumps(ctx))
        except llm.LLMError as e:
            st.error(str(e))
    narrative = st.session_state.get(f"narr_{month}", "")
    if narrative:
        st.markdown(narrative)

    d1, d2 = st.columns(2)
    d1.download_button("⬇️ Download PDF", reports.pdf_bytes(rep, narrative),
                       f"report_{month}.pdf", "application/pdf")
    d2.download_button("⬇️ Download CSV", reports.csv_bytes(rep), f"transactions_{month}.csv", "text/csv")
