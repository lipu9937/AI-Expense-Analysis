import io
import re
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def build(df, budgets, income, month):
    d = df[df["month"] == month]
    total = float(d["amount"].sum())
    cat = (d.groupby("category")["amount"].agg(["sum", "count"])
           .sort_values("sum", ascending=False).reset_index())
    cat.columns = ["Category", "Spent", "Transactions"]
    cat["Share %"] = (cat["Spent"] / total * 100).round(1) if total else 0
    spent = d.groupby("category")["amount"].sum()
    cats = sorted(set(spent.index) | set(budgets))
    bt = pd.DataFrame({"Category": cats,
                       "Spent": [round(float(spent.get(c, 0)), 2) for c in cats],
                       "Budget": [budgets.get(c, 0.0) for c in cats]})
    bt["Difference"] = (bt["Budget"] - bt["Spent"]).round(2)
    bt["Status"] = ["No budget" if b == 0 else ("Over budget" if s > b else "Within budget")
                    for s, b in zip(bt["Spent"], bt["Budget"])]
    tx = d[["date", "description", "category", "payment_method", "amount"]].copy()
    tx["date"] = tx["date"].dt.strftime("%Y-%m-%d")
    return {"month": month, "total": round(total, 2), "income": income,
            "savings": round(income - total, 2) if income else None,
            "count": len(d), "categories": cat, "budget_table": bt, "transactions": tx}


def csv_bytes(rep):
    return rep["transactions"].to_csv(index=False).encode("utf-8")


def _clean(text):
    text = text.replace("₹", "Rs. ")
    return escape(re.sub(r"[*#`]", "", text))


def _table(df):
    if df.empty:
        data = [list(df.columns), ["(No records)"] + [""] * max(len(df.columns) - 1, 0)]
    else:
        data = [list(df.columns)] + df.astype(str).values.tolist()
    t = Table(data, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
    ]
    if len(data) > 1:
        style.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]))
    t.setStyle(TableStyle(style))
    return t


def pdf_bytes(rep, narrative=""):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"Report {rep['month']}")
    s = getSampleStyleSheet()
    sav = "n/a (income not set)" if rep["savings"] is None else f"Rs. {rep['savings']:,.2f}"
    el = [Paragraph(f"Monthly Financial Report - {rep['month']}", s["Title"]),
          Paragraph(f"Total spent: Rs. {rep['total']:,.2f} &nbsp;|&nbsp; Transactions: {rep['count']} "
                    f"&nbsp;|&nbsp; Savings: {sav}", s["Normal"]), Spacer(1, 12),
          Paragraph("Spending by category", s["Heading2"]), _table(rep["categories"]), Spacer(1, 12),
          Paragraph("Budget comparison", s["Heading2"]), _table(rep["budget_table"]), Spacer(1, 12)]
    if narrative:
        el.append(Paragraph("AI summary", s["Heading2"]))
        for para in narrative.split("\n"):
            if para.strip():
                el.append(Paragraph(_clean(para), s["Normal"]))
        el.append(Spacer(1, 12))
    el += [Paragraph("Transactions (first 40)", s["Heading2"]), _table(rep["transactions"].head(40))]
    doc.build(el)
    return buf.getvalue()
