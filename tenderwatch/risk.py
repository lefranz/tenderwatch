"""Shared by the risk indicators: price brackets, binomial test, multiple comparisons, tables.

Every indicator follows the same pattern (docs/indicators/README.md): one
observation per awarded lot, weighted so that a project weighs 1; for each lot,
the rate of similar contracts awarded by OTHER authorities; per authority,
observed against expected under a one-sided binomial, then Benjamini-Hochberg
over all the authorities tested.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from scipy.special import betainc

DEFAULT_BRACKETS = (250_000, 1_000_000, 5_000_000)
UNITS = {"k": 1_000, "M": 1_000_000}


def parse_brackets(text: str) -> tuple[int, ...]:
    """"250k,1M,5M" → (250000, 1000000, 5000000); "none" → () : price not used."""
    if text.strip().lower() == "none":
        return ()
    bounds = []
    for t in text.split(","):
        t = t.strip()
        bounds.append(int(float(t[:-1]) * UNITS[t[-1]]) if t[-1:] in UNITS else int(t))
    if any(b <= 0 for b in bounds) or bounds != sorted(set(bounds)):
        raise ValueError(f"brackets must be positive and increasing: {text}")
    return tuple(bounds)


def label(v: int) -> str:
    for unit, n in (("M", 1_000_000), ("k", 1_000)):
        if v >= n and v % (n // 10) == 0:
            return f"{v / n:g}{unit}"
    return str(v)


def bracket_case(bounds: tuple[int, ...]) -> str:
    """SQL expression giving the price bracket of `price`. Bounds are ints, safe to inline."""
    if not bounds:
        return "'any'"
    bounds = [int(b) for b in bounds]
    whens = [f"WHEN price < {bounds[0]} THEN '<{label(bounds[0])}'"]
    whens += [f"WHEN price < {hi} THEN '{label(lo)}-{label(hi)}'" for lo, hi in zip(bounds, bounds[1:])]
    return ("CASE WHEN price IS NULL THEN 'unknown' " + " ".join(whens)
            + f" ELSE '>={label(bounds[-1])}' END")


def binom_sf(x: float, n: float, p: float) -> float:
    """P(X >= x) for X ~ Binomial(n, p), with real x and n (weighted lots)."""
    if x <= 0:
        return 1.0
    if p <= 0:
        return 0.0
    return float(betainc(x, n - x + 1, p))


def benjamini_hochberg(ps: list[float]) -> list[float]:
    """Benjamini-Hochberg q-values, in the order of the p-values given."""
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    q = [0.0] * m
    prev = 1.0
    for rank, i in reversed(list(enumerate(order, 1))):
        prev = min(prev, ps[i] * m / rank)
        q[i] = prev
    return q


def by_authority(lot_rows: list[dict], min_projects: int, flag: str, name: str) -> list[dict]:
    """Aggregate lots by authority; only those with at least min_projects projects are tested.

    Each lot carries `weight`, `expected` (the rate of similar contracts) and
    `flag` (0 or 1). The weighted count of flagged lots goes out as `name`, the
    raw count as `name + "_lots"`, and the winner of most flagged lots as
    `top_winner`.
    """
    groups = defaultdict(list)
    for r in lot_rows:
        if r["expected"] is not None:
            groups[r["proc_office_id"]].append(r)
    rows = []
    for po, ls in groups.items():
        n = sum(float(r["weight"]) for r in ls)
        if n < min_projects - 1e-9:
            continue
        obs = sum(float(r["weight"]) * r[flag] for r in ls)
        exp = sum(float(r["weight"]) * float(r["expected"]) for r in ls)
        winners = Counter((r["winner"], r["winner_name"]) for r in ls if r[flag])
        (_, winner), k = winners.most_common(1)[0] if winners else ((None, None), 0)
        rows.append({
            "proc_office_id": po, "authority": ls[0]["authority"], "jurisdiction": ls[0]["jurisdiction"],
            "projects": round(n, 1), "lots": len(ls), name + "_lots": sum(r[flag] for r in ls),
            name: round(obs, 1), "expected": round(exp, 1),
            "ratio": round(obs / exp, 2) if exp else None,
            "p": binom_sf(obs, n, exp / n),
            "top_winner": winner, "top_winner_lots": k,
        })
    for r, q in zip(rows, benjamini_hochberg([r["p"] for r in rows])):
        r["q"] = q
    rows.sort(key=lambda r: (r["p"], -r[name]))
    return rows


def _fmt(c, v):
    if v is None:
        return ""
    if c in ("p", "q"):
        return f"{v:.1e}" if v < 0.001 else f"{v:.3f}"
    if c == "expected":
        return f"{float(v):.2f}" if v < 1 else f"{float(v):.1f}"
    return str(v).replace("|", "/").replace("\n", " ")


def _table(rows, cols, numbered=True):
    out = [("| # " if numbered else "") + "| " + " | ".join(cols) + " |",
           "|" + "---|" * (len(cols) + numbered)]
    for i, r in enumerate(rows, 1):
        out.append((f"| {i} " if numbered else "") + "| " + " | ".join(_fmt(c, r[c]) for c in cols) + " |")
    return out
