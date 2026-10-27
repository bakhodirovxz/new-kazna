"""Server tomonidagi ruscha formatlar (qoidalar matni, xlsx sarlavhalari): spec 7.7 / TZ 9."""

from __future__ import annotations

NBSP = " "
MINUS = "−"


def fmt_num(value: float, digits: int = 1) -> str:
    text = f"{abs(value):,.{digits}f}".replace(",", NBSP).replace(".", ",")
    return (MINUS if value < 0 and text.strip("0, ") else "") + text


def fmt_money(mln: float, digits: int = 1) -> str:
    size = abs(mln)
    if size >= 1_000_000:
        return f"{fmt_num(mln / 1_000_000, digits)} трлн"
    if size >= 1_000:
        return f"{fmt_num(mln / 1_000, digits)} млрд"
    return f"{fmt_num(mln, digits)} млн"


def fmt_pct(ratio: float, digits: int = 1) -> str:
    return f"{fmt_num(ratio * 100, digits)}%"
