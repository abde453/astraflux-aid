"""Safe CSV import: preview, column mapping, unit conversion, validation. The raw text is stored untouched elsewhere."""
import csv

MAX_BYTES, MAX_ROWS = 200_000, 2000


class DataError(ValueError):
    """User-facing data problem."""


def _num(x, dec):
    x = x.strip()
    return float(x.replace(",", ".") if dec else x)


def _isnum(x, dec):
    try: _num(x, dec); return True
    except ValueError: return False


def read_table(text: str):
    if len(text.encode("utf-8", "ignore")) > MAX_BYTES: raise DataError("File too large (max 200 KB).")
    lines = [l for l in text.lstrip("\ufeff").splitlines() if l.strip()]
    if len(lines) < 2: raise DataError("The file has no data rows.")
    try: d = csv.Sniffer().sniff("\n".join(lines[:10]), delimiters=",;\t")
    except csv.Error: d = csv.excel
    rows = [r for r in csv.reader(lines, d)]
    if len(rows) > MAX_ROWS + 1: raise DataError(f"Too many rows (max {MAX_ROWS}).")
    dec = d.delimiter == ";" or d.delimiter == "\t"
    header = any(c.strip() and not _isnum(c, dec) for c in rows[0])
    heads = [c.strip() or f"col{i+1}" for i, c in enumerate(rows[0])] if header else [f"col{i+1}" for i in range(len(rows[0]))]
    return heads, rows[1:] if header else rows, dec, d.delimiter


def preview(text: str):
    heads, rows, dec, delim = read_table(text)
    return {"headers": heads, "rows": rows[:10], "n_rows": len(rows), "delimiter": delim, "decimal_comma": dec}


def _col(heads, c):
    if c in heads: return heads.index(c)
    if str(c).isdigit() and int(c) < len(heads): return int(c)
    raise DataError(f"Column '{c}' not found. Available: {', '.join(heads)}")


def process(text, time_col, release_col, time_unit="min", release_unit="percent"):
    if time_unit not in ("min", "h", "s"): raise DataError("time_unit must be min, h or s.")
    if release_unit not in ("percent", "fraction"): raise DataError("release_unit must be percent or fraction.")
    heads, rows, dec, _ = read_table(text)
    ti, ri = _col(heads, time_col), _col(heads, release_col)
    if ti == ri: raise DataError("Time and release must be different columns.")
    k = {"min": 1.0, "h": 60.0, "s": 1 / 60}[time_unit]; m = 100.0 if release_unit == "fraction" else 1.0
    pts, warn, missing = [], [], 0
    for n, r in enumerate(rows, start=2):
        if len(r) <= max(ti, ri) or not r[ti].strip() or not r[ri].strip(): missing += 1; continue
        try: pts.append((_num(r[ti], dec) * k, _num(r[ri], dec) * m))
        except ValueError: raise DataError(f"Row {n}: non-numeric value ('{r[ti]}', '{r[ri]}').")
    if missing: warn.append(f"{missing} row(s) with missing values were ignored.")
    if len(pts) < 3: raise DataError("At least 3 valid data points are required.")
    if any(t < 0 for t, _ in pts): raise DataError("Negative time values are not allowed.")
    ts = [t for t, _ in pts]
    dup = sorted({round(t, 6) for t in ts if ts.count(t) > 1})
    if dup: raise DataError(f"Duplicate time points (min): {dup[:5]}. Average replicates before import.")
    if ts != sorted(ts): pts.sort(); warn.append("Rows were not in time order and were sorted.")
    if any(v < 0 or v > 110 for _, v in pts): raise DataError("Release values must be within 0-100 % (check release_unit).")
    if any(v > 100 for _, v in pts): warn.append("Some values exceed 100 % (assay noise?).")
    if max(v for _, v in pts) <= 1.0 and release_unit == "percent": warn.append("All values are <= 1 %: is the release in fractions?")
    return [[round(t, 6), round(v, 6)] for t, v in pts], warn
