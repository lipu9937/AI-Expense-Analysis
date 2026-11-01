import json

import numpy as np
import pandas as pd

FLEX = ["Food & Dining", "Shopping", "Entertainment", "Subscriptions", "Travel", "Personal Care"]


def monthly_totals(df):
    return df.groupby("month")["amount"].sum().round(2)


def category_matrix(df):
    return df.pivot_table(index="month", columns="category", values="amount",
                          aggfunc="sum", fill_value=0).round(2)


def category_change(df):
    m = category_matrix(df)
    if len(m) < 2:
        return pd.DataFrame(columns=["Category", "Previous", "Current", "Change", "Change %"])
    prev, cur = m.iloc[-2], m.iloc[-1]
    out = pd.DataFrame({"Category": m.columns, "Previous": prev.values, "Current": cur.values})
    out["Change"] = (out["Current"] - out["Previous"]).round(2)
    out["Change %"] = np.where(out["Previous"] > 0, (out["Change"] / out["Previous"] * 100).round(1), np.nan)
    return out.sort_values("Change", ascending=False).reset_index(drop=True)


def repeated(df, min_count=3):
    key = (df["description"].str.lower().str.replace(r"[^a-z ]", " ", regex=True)
           .str.split().str[:3].str.join(" "))
    g = df.assign(merchant=key).groupby("merchant")["amount"].agg(["count", "sum", "mean"]).reset_index()
    g = g[(g["count"] >= min_count) & (g["merchant"] != "")].sort_values("sum", ascending=False).head(10)
    g.columns = ["Merchant", "Count", "Total", "Average"]
    return g.round(2)


def anomalies(df):
    cols = ["date", "description", "category", "amount", "category_average"]
    rows = []
    for cat, g in df.groupby("category"):
        if len(g) < 4:
            continue
        mu, sd = g["amount"].mean(), g["amount"].std()
        if sd and sd > 0:
            for _, r in g[g["amount"] > mu + 2 * sd].iterrows():
                rows.append({"date": r["date"].date().isoformat(), "description": r["description"],
                             "category": cat, "amount": r["amount"], "category_average": round(mu, 2)})
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows).sort_values("amount", ascending=False).head(10)


def forecast(df):
    mt = monthly_totals(df)
    if len(mt) >= 3:
        y = mt.values[-6:]
        slope, icpt = np.polyfit(np.arange(len(y)), y, 1)
        total, method = max(float(slope * len(y) + icpt), 0.0), "linear trend over last 6 months"
    else:
        total, method = float(mt.mean()) if not mt.empty else 0.0, "average of available months"
    avg = category_matrix(df).tail(3).mean().round(2)
    return {"next_month_total": round(total, 2), "method": method,
            "note": "latest month may be incomplete, which can bias the forecast",
            "category_avg_last_3_months": avg.to_dict()}


def recommended_budgets(df):
    avg = category_matrix(df).tail(3).mean()
    rec = {c: float(np.round(v * (0.9 if c in FLEX else 1.0) / 50) * 50) for c, v in avg.items() if v > 0}
    return rec


def build_context(df, budgets, income, extra=None):
    """Everything the LLM may use. All numbers are computed here with Pandas."""
    if df.empty:
        return {}
    mt = monthly_totals(df)
    cur = mt.index[-1]
    m = category_matrix(df)
    cur_cat = m.loc[cur]
    ctx = {
        "currency": "INR",
        "data_range": [df["date"].min().date().isoformat(), df["date"].max().date().isoformat()],
        "current_month": cur,
        "note": "'current_month' is the latest month that has data",
        "monthly_income": income or None,
        "monthly_totals": mt.to_dict(),
        "current_month_savings": round(income - mt[cur], 2) if income else None,
        "current_month_by_category": cur_cat[cur_cat > 0].sort_values(ascending=False).to_dict(),
        "category_by_month": m.to_dict("index"),
        "category_change_vs_previous_month": category_change(df).to_dict("records"),
        "budgets": budgets,
        "budget_status_current_month": {c: {"budget": b, "spent": float(cur_cat.get(c, 0))}
                                        for c, b in budgets.items()},
        "payment_method_totals": df.groupby("payment_method")["amount"].sum().round(2).to_dict(),
        "repeated_expenses": repeated(df).to_dict("records"),
        "unusual_transactions": anomalies(df).to_dict("records"),
        "forecast": forecast(df),
        "recent_transactions": [
            {"date": r.date.date().isoformat(), "description": r.description,
             "amount": r.amount, "category": r.category}
            for r in df.head(30).itertuples()],
    }
    if extra:
        ctx.update(extra)
    return json.loads(json.dumps(ctx, default=str).replace("NaN", "null"))
