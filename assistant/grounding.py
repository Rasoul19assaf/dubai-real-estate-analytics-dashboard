"""Figure check: every number in an answer must trace back to something the tools returned.

A language model can state a plausible figure it never looked up. The prompt forbids that, but a
prompt is a request, not a control. This module is the control: it extracts the numbers from the
answer and looks for each one in the SQL results and retrieved documents of the same run
(allowing for rounding and for ratios shown as percentages).

Ignored: numbers that appear in the question itself, years, and small counts up to 12
(ranks, "top 5", months), which are wording rather than data.
"""
from __future__ import annotations

import re

_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def _parse(text: str) -> list[tuple[float, int]]:
    """(value, decimals shown) for each number in text. A plain 4-digit 19xx/20xx token (no
    thousands separator) is a year and gets decimals = -1 so callers can skip it."""
    out = []
    for m in _NUM.finditer(text or ""):
        raw = m.group(0).replace(",", "").rstrip(".")
        try:
            if "," not in m.group(0) and "." not in raw and 1900 <= float(raw) <= 2100:
                out.append((float(raw), -1))
                continue
            out.append((float(raw), len(raw.split(".")[1]) if "." in raw else 0))
        except ValueError:
            pass
    return out


def _pool(sql_results, docs) -> list[float]:
    vals: list[float] = []
    for res in sql_results:
        if res.error:
            continue
        vals.append(float(len(res.rows)))
        for row in res.rows:
            for cell in row:
                if isinstance(cell, bool) or cell is None:
                    continue
                if isinstance(cell, (int, float)):
                    vals.append(float(cell))
                else:
                    vals.extend(v for v, _ in _parse(str(cell)))
    for d in docs:
        vals.extend(v for v, _ in _parse(d.text))
    return vals


def _matches(n: float, decimals: int, pool: list[float]) -> bool:
    for v in pool:
        for cand in (v, v * 100, v / 1e6, v / 1e3):          # as is, ratio as %, in millions, in thousands
            if round(cand, max(decimals, 0)) == n or (cand and abs(n - cand) / abs(cand) <= 0.005):
                return True
    return False


def check_figures(answer: str, question: str, sql_results, docs) -> tuple[int, list[str]]:
    """Returns (figures checked, figures NOT found in the tool outputs)."""
    asked = {v for v, _ in _parse(question)}
    pool = _pool(sql_results, docs)
    checked, missing = 0, []
    for n, dec in _parse(answer):
        if n in asked or dec == -1 or (dec == 0 and n <= 12):
            continue
        checked += 1
        if not _matches(n, dec, pool):
            missing.append(f"{n:,.{dec}f}")
    return checked, list(dict.fromkeys(missing))
