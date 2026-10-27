"""Sintetik g'aznachilik modeli: bank проводкалари, hisob qoldiqlari, shartnomalar.

Qoldiqlar проводкалардan hisoblanadi: yopilish = ochilish + ЧДП + «Разница», bu yerda
|Разница| ≤ 0,4% oborot (prototip `diff`) — sifat tekshiruvi 2 har doim o'tadi.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from functools import cached_property
from random import Random

from app.dwh.dates import add_months, month_end, month_id, month_start
from app.etl.synthetic.reference import (
    BANKS,
    BRANCHES,
    EXPENSE_ITEMS,
    HQ_ID,
    INCOME_ITEMS,
    OBJECTS,
    OTHER_COUNTERPARTIES,
    SUPPLIER_CODES,
    BranchRef,
    CashItem,
    share,
)
from app.etl.synthetic.rng import rnd

HISTORY_START = date(2024, 1, 1)
CONTRACT_EPOCH = date(2024, 1, 1)  # shartnoma sanalari as_of'ga bog'liq bo'lmasligi uchun
FLOOR_HORIZON = date(2035, 12, 31)  # ochilish qoldig'i pasti hisoblanadigan qat'iy gorizont
_ACCOUNT_FLOORS: dict[tuple[int, date, int], list[Decimal]] = {}  # (seed, history_start, filial)
YEAR_FACTOR = {2024: 0.82, 2025: 0.91}  # 2026 = 1.0 (prototip "2025" ≈ 0,86–0,96)


def money(value: float | Decimal) -> Decimal:
    return Decimal(f"{float(value):.2f}")


def workdays(month: date) -> list[date]:
    days = (month.replace(day=d) for d in range(1, month_end(month).day + 1))
    return [d for d in days if d.weekday() < 5]


@dataclass(frozen=True, slots=True)
class Posting:
    branch_id: int
    item_code: str
    direction: str
    day: date
    amount: Decimal
    bank: int
    cp_code: str | None
    contract_code: str | None
    gl_account: str
    src_id: str


@dataclass(frozen=True, slots=True)
class BalanceRow:
    branch_id: int
    bank: int
    day: date
    balance: Decimal


@dataclass(frozen=True, slots=True)
class ContractRef:
    code: str
    number: str
    branch_id: int
    cp_code: str
    kind: str  # receivable | payable
    contract_date: date
    end_date: date
    due_date: date
    amount: Decimal
    late: bool
    overdue_ratio: float
    object_code: str | None


@dataclass(frozen=True, slots=True)
class CashModel:
    postings: list[Posting]
    full_amounts: dict[tuple[int, int, str], float]  # (filial, oy, statya) → to'liq oy summasi
    balances: list[BalanceRow]


def _season(seed: int, item: CashItem, ym: int) -> float:
    r = rnd(seed, "season", item.code, ym)
    if item.lumpy:
        return 0.0 if r.random() < 0.3 else r.uniform(0.6, 1.9)
    return r.uniform(item.lo, item.hi)


def _counterparty(r: Random, item: CashItem, branch: BranchRef) -> str | None:
    if item.direction == "out":
        return r.choice(SUPPLIER_CODES)
    if item.code == "PKM54-I01":
        return "CP-013" if branch.id == HQ_ID else r.choice(("CP-013", "CP-014"))
    return {"PKM54-I02": "CP-016", "PKM54-I03": "CP-015"}.get(item.code)


def _gl_account(item: CashItem) -> str:
    # 5210 — valyuta hisobi (XMI kreditlari), 5530 — maxsus hisob (byudjet), qolgani 5110.
    return {"PKM54-I02": "5210", "PKM54-I03": "5530"}.get(item.code, "5110")


class SynthModel:
    def __init__(self, seed: int, as_of: date, history_start: date = HISTORY_START) -> None:
        self.seed = seed
        self.as_of = as_of
        self.history_start = history_start

    def months(self) -> list[date]:
        out: list[date] = []
        cur = month_start(self.history_start)
        while cur <= self.as_of:
            out.append(cur)
            cur = add_months(cur, 1)
        return out

    def period_end(self, month: date) -> date:
        return min(month_end(month), self.as_of)

    @cached_property
    def bank_shares(self) -> dict[int, list[float]]:
        out: dict[int, list[float]] = {}
        for branch in BRANCHES:
            r = rnd(self.seed, "bank", branch.id)
            raw = [r.random() ** 2 + 0.05 for _ in BANKS]
            total = sum(raw)
            out[branch.id] = [x / total for x in raw]
        return out

    @cached_property
    def contracts(self) -> list[ContractRef]:
        out: list[ContractRef] = []
        for branch in BRANCHES:
            monthly_out = sum(e.base * share(branch, e.hq_share) for e in EXPENSE_ITEMS)
            objects = [f"OBJ-{i + 1:02d}" for i, o in enumerate(OBJECTS) if o[1] + 1 == branch.id]
            for n in range(1, 4):
                r = rnd(self.seed, "contract", branch.id, n)
                kind = "receivable" if r.random() < 0.45 else "payable"
                if kind == "payable" or branch.id == HQ_ID:
                    cp = r.choice(SUPPLIER_CODES)
                else:
                    cp = r.choice(tuple(c for c, _, k in OTHER_COUNTERPARTIES if k == "buyer"))
                signed = CONTRACT_EPOCH + timedelta(days=r.randint(0, 900))
                with_object = kind == "payable" and bool(objects) and r.random() < 0.5
                obj = r.choice(objects) if with_object else None
                out.append(ContractRef(
                    code=f"CTR-{branch.id:02d}-{n}",
                    number=f"№ {r.randint(12, 480)}/{signed.year}",
                    branch_id=branch.id,
                    cp_code=cp,
                    kind=kind,
                    contract_date=signed,
                    end_date=signed + timedelta(days=r.randint(180, 720)),
                    due_date=signed + timedelta(days=r.randint(60, 240)),
                    amount=money(monthly_out * r.uniform(0.06, 0.28)),
                    late=r.random() < 0.45,
                    overdue_ratio=r.uniform(0.3, 0.9),
                    object_code=obj,
                ))
        return out

    @cached_property
    def cash(self) -> CashModel:
        postings: list[Posting] = []
        full: dict[tuple[int, int, str], float] = {}
        for branch in BRANCHES:
            payables = [c for c in self.contracts
                        if c.branch_id == branch.id and c.kind == "payable"]
            for month in self.months():
                ym = month_id(month)
                for item, amount in self._month_amounts(branch, month):
                    full[(branch.id, ym, item.code)] = amount
                    postings.extend(self._split(branch, item, month, amount, payables))
        postings.sort(key=lambda p: (p.day, p.src_id))
        return CashModel(postings, full, self._balances(postings))

    def _month_amounts(self, branch: BranchRef, month: date) -> list[tuple[CashItem, float]]:
        """Filial-oy to'liq summalari — as_of'dan butunlay mustaqil (sof funksiya)."""
        ym = month_id(month)
        factor = YEAR_FACTOR.get(month.year, 1.0)
        out: list[tuple[CashItem, float]] = []
        for item in (*INCOME_ITEMS, *EXPENSE_ITEMS):
            item_share = share(branch, item.hq_share)
            if item_share <= 0:
                continue
            r = rnd(self.seed, "amt", branch.id, item.code, ym)
            amount = (item.base * item_share * _season(self.seed, item, ym) * factor
                      * r.uniform(0.9, 1.1))
            if amount >= 1:
                out.append((item, amount))
        return out

    def _opening_floor(self, branch: BranchRef) -> Decimal:
        """Filial qoldig'i hech qachon manfiy bo'lmasligi uchun minimal ochilish qoldig'i.

        Qat'iy gorizont (`FLOOR_HORIZON`) bo'yicha eng chuqur kumulyativ kamayish + bitta
        oy chiqimi zaxirasi. Gorizont as_of'ga bog'liq emas — shuning uchun o'tgan
        qoldiqlar as_of o'zgarganda siljimaydi."""
        running = low = peak_out = 0.0
        month = month_start(self.history_start)
        while month <= FLOOR_HORIZON:
            inflow = outflow = 0.0
            for item, amount in self._month_amounts(branch, month):
                if item.direction == "in":
                    inflow += amount
                else:
                    outflow += amount
            running += inflow - outflow - 0.004 * (inflow + outflow)  # «Разница»ning eng yomoni
            low = min(low, running)
            peak_out = max(peak_out, outflow)
            month = add_months(month, 1)
        return money(-low + peak_out)

    def _split(self, branch: BranchRef, item: CashItem, month: date, amount: float,
               payables: list[ContractRef], until: date | None = None) -> list[Posting]:
        ym = month_id(month)
        r = rnd(self.seed, "post", branch.id, item.code, ym)
        count = 1 if item.lumpy else r.randint(1, 4)
        days = sorted(r.sample(workdays(month), count))
        weights = [r.uniform(0.5, 1.5) for _ in days]
        parts = [money(amount * w / sum(weights)) for w in weights]
        parts[-1] = money(amount) - sum(parts[:-1], Decimal(0))  # yaxlitlash qoldig'i
        shares = self.bank_shares[branch.id]
        out: list[Posting] = []
        for n, (day, value) in enumerate(zip(days, parts, strict=True), start=1):
            # Tasodifiy qiymatlar filtrdan OLDIN olinadi — o'tgan oylar as_of'ga bog'liq emas.
            bank = r.choices(range(len(BANKS)), weights=shares)[0]
            cp = _counterparty(r, item, branch)
            eligible = [c.code for c in payables if c.contract_date <= day]
            contract = (r.choice(eligible)
                        if item.code in ("PKM54-O01", "PKM54-O02") and eligible else None)
            if day > (until or self.as_of) or value <= 0:
                continue
            out.append(Posting(branch.id, item.code, item.direction, day, value, bank, cp,
                               contract, _gl_account(item),
                               f"CF-{branch.id:02d}-{item.code}-{ym}-{n}"))
        return out

    def _account_floor(self, branch: BranchRef) -> list[Decimal]:
        """Har hisob qoldig'i manfiy bo'lmasligi uchun minimal ochilish: `FLOOR_HORIZON`gacha
        hisobning eng chuqur kumulyativ kamayishi + bitta oy chiqimi (`_opening_floor` kabi,
        as_of'ga bog'liq emas — o'tgan qoldiqlar siljimaydi). Faqat seed va history_start'ga
        bog'liq — kesh modellar orasida umumiy (sinovlar bir seed'ni ko'p as_of bilan quradi)."""
        key = (self.seed, self.history_start, branch.id)
        if key not in _ACCOUNT_FLOORS:
            _ACCOUNT_FLOORS[key] = self._account_floor_uncached(branch)
        return _ACCOUNT_FLOORS[key]

    def _account_floor_uncached(self, branch: BranchRef) -> list[Decimal]:
        payables = [c for c in self.contracts if c.branch_id == branch.id and c.kind == "payable"]
        n = len(BANKS)
        running, low, peak_out = [0.0] * n, [0.0] * n, [0.0] * n
        month = month_start(self.history_start)
        while month <= FLOOR_HORIZON:
            inflow, outflow = [0.0] * n, [0.0] * n
            for item, amount in self._month_amounts(branch, month):
                for p in self._split(branch, item, month, amount, payables, until=FLOOR_HORIZON):
                    (inflow if p.direction == "in" else outflow)[p.bank] += float(p.amount)
            for k in range(n):
                running[k] += inflow[k] - outflow[k] - 0.004 * (inflow[k] + outflow[k])
                low[k] = min(low[k], running[k])
                peak_out[k] = max(peak_out[k], outflow[k])
            month = add_months(month, 1)
        return [money(-low[k] + peak_out[k]) for k in range(n)]

    def _balances(self, postings: list[Posting]) -> list[BalanceRow]:
        """Har hisob qoldig'i oy sayin: ochilish + shu hisobning ЧДП + «Разница» (filial-oy
        nisbati × hisob oboroti). Tenglik hisob darajasida ham saqlanadi — qo'lda kiritilgan
        qoldiq faqat o'z hisobini sifat tekshiruvidan chiqaradi (A-ME.R1). Ochilish qatori har
        doim `history_start - 1 kun`da (oyna 1-kundan boshlansa sifat tekshiruvi uni ko'radi)."""
        net: dict[tuple[int, int, int], Decimal] = defaultdict(Decimal)
        turnover: dict[tuple[int, int, int], Decimal] = defaultdict(Decimal)
        for p in postings:
            key = (p.branch_id, p.bank, month_id(p.day))
            net[key] += p.amount if p.direction == "in" else -p.amount
            turnover[key] += p.amount
        opening_day = self.history_start - timedelta(days=1)
        rows: list[BalanceRow] = []
        for branch in BRANCHES:
            r0 = rnd(self.seed, "open", branch.id)
            open0 = money(r0.uniform(820000, 900000) if branch.id == HQ_ID
                          else r0.uniform(18000, 32000) * branch.weight)
            total = max(open0, self._opening_floor(branch))
            accounts = [max(part.balance, floor) for part, floor in zip(
                self._split_balance(branch.id, opening_day, total),
                self._account_floor(branch), strict=True)]
            rows += [BalanceRow(branch.id, k, opening_day, v) for k, v in enumerate(accounts)]
            for month in self.months():
                ym = month_id(month)
                rd = rnd(self.seed, "diff", branch.id, ym)
                ratio = -rd.uniform(0, 0.004) if rd.random() < 0.75 else rd.uniform(0, 0.0015)
                for k in range(len(accounts)):
                    accounts[k] += net.get((branch.id, k, ym), Decimal(0)) + money(
                        float(turnover.get((branch.id, k, ym), Decimal(0))) * ratio)
                day = self.period_end(month)
                rows += [BalanceRow(branch.id, k, day, v) for k, v in enumerate(accounts)]
        return rows

    def _split_balance(self, branch_id: int, day: date, total: Decimal) -> list[BalanceRow]:
        shares = self.bank_shares[branch_id]
        parts = [money(total * Decimal(s)) for s in shares]
        parts[-1] = total - sum(parts[:-1], Decimal(0))  # yaxlitlash qoldig'i
        return [BalanceRow(branch_id, k, day, v) for k, v in enumerate(parts)]
