"""ParsedFile → staging (S2 spec 3.2): hisob moslashtirish, ko'chirma balansi tekshiruvi,
valyuta kursi, kontragent (faqat yuridik shaxs), idempotentlik kalitlari (manba, hujjat turi,
tashqi id — TZ 8). Xatolar ReportingSink.error ga (hisob raqami maskalangan).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from app.core.crypto import blind_index
from app.dwh.dates import date_id
from app.etl.banks.accounts import AccountIndex
from app.etl.banks.fx import FxLookup
from app.etl.banks.models import BalanceRow, LineRow, ParsedFile, mask
from app.etl.banks.registry import BANKS, BankAccount
from app.etl.types import ReportingSink

ERROR_LIMIT = 1000
MLN = Decimal(1_000_000)
CENT = Decimal("0.01")
TOLERANCE = Decimal("0.01")


def to_mln(amount: Decimal, rate: Decimal) -> Decimal:
    return (amount * rate / MLN).quantize(CENT, rounding=ROUND_HALF_EVEN)


@dataclass
class _Group:
    opening: BalanceRow | None = None
    closing: BalanceRow | None = None
    lines: list[LineRow] = field(default_factory=list)

    def first_line(self) -> int:
        marks = [x.line for x in self.lines]
        marks += [x.line for x in (self.opening, self.closing) if x is not None]
        return min(marks)


class BankMapper:
    def __init__(self, sink: ReportingSink, accounts: AccountIndex, fx: FxLookup, *,
                 index_key: bytes) -> None:
        self.sink = sink
        self.accounts = accounts
        self.fx = fx
        self.index_key = index_key
        self.errors = 0
        self._banks: set[str] = set()
        self._cps: set[str] = set()

    def report(self, where: str, code: str, message: str) -> None:
        self.errors += 1
        if self.errors <= ERROR_LIMIT:
            self.sink.error(target="bank_file", code=code, src_id=mask(where),
                            message=mask(f"{where}: {message}"))

    def stage(self, bank_code: str, file: str, parsed: ParsedFile) -> int:
        for err in parsed.errors:
            self.report(f"{file}:{err.line}", "bad_row", err.message)
        reported: set[str] = set()
        docs: set[tuple[str, str]] = set()
        if parsed.kind == "statement":
            return self._statement(bank_code, file, parsed, reported, docs)
        return self._orders(bank_code, file, parsed, reported, docs)

    # ── Yordamchilar ────────────────────────────────────────────────
    def _resolve(self, bank_code: str, where: str, account: str,
                 reported: set[str]) -> BankAccount | None:
        acc = self.accounts.resolve(account)
        if acc is None:
            if account not in reported:
                reported.add(account)
                self.report(where, "unknown_account",
                            f"счёт …{account[-4:]} не сопоставлен с филиалом (banks.accounts)")
            return None
        if acc.bank_code != bank_code:
            if account not in reported:
                reported.add(account)
                self.report(where, "wrong_bank",
                            f"счёт …{acc.last4} открыт в банке «{acc.bank_code}», "
                            f"файл — в каталоге «{bank_code}»")
            return None
        return acc

    def _rate(self, where: str, acc: BankAccount, day: date) -> Decimal | None:
        rate = self.fx.rate(acc.currency, day)
        if rate is None:
            self.report(where, "fx_rate_missing",
                        f"нет курса ЦБ {acc.currency} на {day:%d.%m.%Y} (счёт …{acc.last4})")
        return rate

    def _bank(self, acc: BankAccount, account: str) -> None:
        if acc.code not in self._banks:
            self._banks.add(acc.code)
            # account_number staging'da shifrlanadi (dim_bank.account_enc + account_bidx).
            self.sink.add("dim_bank", {"code": acc.code, "bank_name": BANKS[acc.bank_code],
                                       "account_number": account, "currency": acc.currency})

    def _counterparty(self, inn: str | None, name: str | None) -> str | None:
        # Faqat yuridik shaxs (9 xonali INN); jismoniy shaxs (ПИНФЛ, INN yo'q) — shaxsiy
        # ma'lumot saqlanmaydi (S2 spec 3.2).
        if inn is None or len(inn) != 9 or not name:
            return None
        code = "CP-" + blind_index(self.index_key, "inn", inn).hex()[:16]
        if code not in self._cps:
            self._cps.add(code)
            self.sink.add("dim_counterparty", {"code": code, "name": name, "kind": "other",
                                               "inn": inn})
        return code

    @staticmethod
    def _extras(row: dict[str, Any], item_code: str | None, cp_code: str | None) -> None:
        if item_code:
            row["item_code"] = item_code  # yo'q bo'lsa merge «Прочие» + ogohlantirish
        if cp_code:
            row["cp_code"] = cp_code

    def _statement(self, bank_code: str, file: str, parsed: ParsedFile, reported: set[str],
                   docs: set[tuple[str, str]]) -> int:
        groups: dict[tuple[str, date], _Group] = {}
        for b in parsed.balances:
            group = groups.setdefault((b.account, b.day), _Group())
            if b.kind == "OB":
                group.opening = b
            else:
                group.closing = b
        for ln in parsed.lines:
            groups.setdefault((ln.account, ln.day), _Group()).lines.append(ln)
        staged = 0
        for (account, day), g in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            where = f"{file}:{g.first_line()}"
            acc = self._resolve(bank_code, where, account, reported)
            if acc is None:
                continue
            if g.opening is not None and g.closing is not None:
                moved = sum((x.amount if x.direction == "in" else -x.amount for x in g.lines),
                            Decimal(0))
                if abs(g.opening.amount + moved - g.closing.amount) > TOLERANCE:
                    self.report(where, "statement_mismatch",
                                f"выписка по счёту …{acc.last4} за {day:%d.%m.%Y} не сходится: "
                                "входящий остаток + обороты ≠ исходящий остаток")
                    continue
            rate = self._rate(where, acc, day)
            if rate is None:
                continue
            self._bank(acc, account)
            if g.closing is not None:
                self.sink.add("fact_balance", {
                    "doc_type": "bank_balance", "src_id": f"{acc.code}:{date_id(day)}",
                    "date_id": date_id(day), "branch_code": acc.branch_code,
                    "bank_code": acc.code, "balance": to_mln(g.closing.amount, rate)})
                staged += 1
            for ln in g.lines:
                if (acc.code, ln.doc_id) in docs:
                    self.report(f"{file}:{ln.line}", "duplicate_doc",
                                f"повтор проводки {ln.doc_id}")
                    continue
                docs.add((acc.code, ln.doc_id))
                row: dict[str, Any] = {
                    "doc_type": "bank_statement", "src_id": f"{acc.code}:{ln.doc_id}",
                    "date_id": date_id(day), "branch_code": acc.branch_code,
                    "direction": ln.direction, "amount": to_mln(ln.amount, rate),
                    "gl_account": acc.gl_account, "bank_code": acc.code}
                self._extras(row, ln.item_code, self._counterparty(ln.cp_inn, ln.cp_name))
                self.sink.add("fact_cashflow", row)
                staged += 1
        return staged

    def _orders(self, bank_code: str, file: str, parsed: ParsedFile, reported: set[str],
                docs: set[tuple[str, str]]) -> int:
        staged = 0
        for o in parsed.orders:
            where = f"{file}:{o.line}"
            acc = self._resolve(bank_code, where, o.account, reported)
            if acc is None:
                continue
            if (acc.code, o.doc_id) in docs:
                self.report(where, "duplicate_doc", f"повтор поручения {o.doc_id}")
                continue
            docs.add((acc.code, o.doc_id))
            rate = self._rate(where, acc, o.day)
            if rate is None:
                continue
            self._bank(acc, o.account)
            row: dict[str, Any] = {
                "doc_type": "bank_payment_order", "src_id": f"{acc.code}:{o.doc_id}",
                "date_id": date_id(o.day), "branch_code": acc.branch_code,
                "bank_code": acc.code, "amount": to_mln(o.amount, rate), "status": o.status,
                "status_date_id": None if o.status_day is None else date_id(o.status_day)}
            self._extras(row, o.item_code, self._counterparty(o.cp_inn, o.cp_name))
            self.sink.add("fact_payment_order", row)
            staged += 1
        return staged
