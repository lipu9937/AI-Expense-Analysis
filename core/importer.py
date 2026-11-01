import pandas as pd

ALIASES = {
    "date": ["date", "txn date", "transaction date", "value date", "posting date"],
    "description": ["description", "narration", "particulars", "details", "remarks", "transaction remarks"],
    "debit": ["debit", "withdrawal", "withdrawal amt", "dr", "debit amount"],
    "amount": ["amount", "transaction amount"],
}


def read_file(file):
    name = file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(file, skip_blank_lines=True)
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(file)
    else:
        raise ValueError("Unsupported file type. Upload a CSV or Excel file.")
    df = df.dropna(how="all")
    if df.empty:
        raise ValueError("The file contains no rows.")
    return df


def detect_columns(cols):
    low = {c: str(c).strip().lower() for c in cols}
    found = {}
    for key, names in ALIASES.items():
        for c, l in low.items():
            if l in names:
                found[key] = c
                break
        else:
            for c, l in low.items():
                if any(n in l for n in names if len(n) > 3):
                    found[key] = c
                    break
    return found


def _num(s):
    return pd.to_numeric(s.astype(str).str.replace(r"[^\d.\-]", "", regex=True), errors="coerce")


def _parse_date(s):
    dt = pd.to_datetime(s, format="ISO8601", errors="coerce")
    if dt.isna().all() and not s.dropna().empty:
        dt = pd.to_datetime(s, format="mixed", dayfirst=True, errors="coerce")
    elif dt.isna().any():
        fallback = pd.to_datetime(s, format="mixed", dayfirst=True, errors="coerce")
        dt = dt.fillna(fallback)
    return dt


def normalize(df, m):
    """m: mapping with date, description and (debit or amount). Returns expense rows only."""
    if not m.get("date") or not m.get("description") or not (m.get("debit") or m.get("amount")):
        raise ValueError("Select a date column, a description column, and a debit or amount column.")
    out = pd.DataFrame({
        "date": _parse_date(df[m["date"]]),
        "description": df[m["description"]].astype(str).str.strip(),
    })
    if m.get("debit"):
        out["amount"] = _num(df[m["debit"]])
    else:
        a = _num(df[m["amount"]])
        out["amount"] = -a.where(a < 0) if (a < 0).any() else a  # negatives = spending
    out = out.dropna(subset=["date", "amount"])
    out = out[(out["amount"] > 0) & (out["description"] != "") & (out["description"].str.lower() != "nan")]
    out["amount"] = out["amount"].round(2)
    out["seq"] = out.groupby(["date", "description", "amount"]).cumcount()
    return out.reset_index(drop=True)
