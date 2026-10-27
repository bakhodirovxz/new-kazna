"""«Ввод данных»: shablonlar va CSV/XLSX import (hammasi yoki hech narsa, ZIP/XML bomb, makros)."""

from __future__ import annotations

import hashlib
import io
import json
import resource
import zipfile
from collections.abc import Callable, Iterator
from datetime import datetime
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from app.main import create_app
from app.manual import imports
from app.manual.entities import ENTITIES
from tests.helpers import SeedUser, login
from tests.manual_helpers import audit_rows, branch_code, migrator_sql, seed_dwh_bank

pytestmark = pytest.mark.usefixtures("clean_manual")
MakeUser = Callable[..., SeedUser]
BANK = "BA-t7bank0000000001"
BALANCE = ENTITIES["kazna.balance"]
CSV = "text/csv"
XLSX = imports.XLSX_TYPE
URL = "/api/v1/data/entities/kazna.balance/import?branch_id=1"
HEAD = "branch_code;bank_code;date;balance"


@pytest.fixture
def client_for() -> Iterator[Callable[[SeedUser], TestClient]]:
    opened: list[TestClient] = []

    def make(user: SeedUser) -> TestClient:
        client = TestClient(create_app(), base_url="https://testserver")
        client.__enter__()
        opened.append(client)
        return login(client, user)

    seed_dwh_bank(BANK)
    yield make
    for client in opened:
        client.__exit__(None, None, None)


def _row(day: str = "2026-09-30", value: str = "1500.00") -> str:
    return f"{branch_code(1)};{BANK};{day};{value}"


def _csv(*rows: str, head: str = HEAD, bom: bool = True) -> bytes:
    return (("﻿" if bom else "") + "\r\n".join([head, *rows]) + "\r\n").encode()


def _post(client: TestClient, body: bytes, ctype: str = CSV, name: str = "ostatki.csv",
          url: str = URL):  # type: ignore[no-untyped-def]
    return client.post(url, content=body, headers={
        "Content-Type": ctype, "X-File-Name": quote(name)})


def _xlsx(rows: list[list[object]], header: list[str] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(header or [f.name for f in BALANCE.fields])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _batches() -> int:
    return int(migrator_sql("SELECT count(*) FROM core.manual_batch")[0][0])


def _entries() -> int:
    return int(migrator_sql("SELECT count(*) FROM core.manual_entry")[0][0])


def _codes(r) -> list[tuple[int, str, str]]:  # type: ignore[no-untyped-def]
    return [(x["row"], x["field"], x["code"]) for x in r.json()["error"]["params"]["rows"]]


def test_csv_import_creates_draft(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    body = _csv(_row(), _row("2026-08-29", "20.50"))
    r = _post(maker, body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["status"] == "draft" and out["rows"] == 2 and out["origin"] == "import"
    name, sha = migrator_sql("SELECT file_name, file_sha256 FROM core.manual_batch")[0]
    assert (name, bytes(sha)) == ("ostatki.csv", hashlib.sha256(body).digest())
    ev = [a for a in audit_rows("data.imported") if a["result"] == "ok"]
    assert len(ev) == 1
    assert ev[0]["details"]["sha256"] == hashlib.sha256(body).hexdigest()
    assert ev[0]["details"]["rows"] == 2 and ev[0]["details"]["file_name"] == "ostatki.csv"
    assert "1500" not in json.dumps(ev[0]["details"])  # mazmun auditda yo'q


def test_bom_and_comma_decimal(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    r = _post(maker, _csv(_row(value="1234,50"), bom=False))
    assert r.status_code == 201, r.text
    assert _post(maker, _csv(_row("2026-08-29", "7,25"), bom=True)).status_code == 201
    vals = migrator_sql("SELECT payload ->> 'balance' FROM core.manual_entry ORDER BY id")
    assert [v[0] for v in vals] == ["1234.50", "7.25"]


def test_thousands_separator_rejected(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    r = _post(maker, _csv(_row(value="1 234,50")))
    assert r.status_code == 422 and r.json()["error"]["code"] == "import_invalid"
    assert _codes(r) == [(2, "balance", "invalid_value")]
    assert _batches() == 0


def test_bad_header(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    for head in (HEAD + ";extra", "branch_code;bank_code;date"):
        r = _post(maker, _csv(_row(), head=head))
        assert r.status_code == 422 and _codes(r) == [(1, "", "bad_header")]
    assert _batches() == 0


def test_all_or_nothing(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    r = _post(maker, _csv(_row(), _row("2026-08-29", "1.005"), _row("2026-07-28")))
    assert r.status_code == 422 and r.json()["error"]["code"] == "import_invalid"
    assert _codes(r) == [(3, "balance", "invalid_value")]  # fayl qatori (1 = sarlavha)
    assert _batches() == 0 and _entries() == 0


def test_5001_rows_rejected(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    r = _post(maker, _csv(*["a;b;c;d"] * 5001))
    assert r.status_code == 422 and _codes(r) == [(5002, "", "too_many_rows")]
    assert _batches() == 0


def test_xlsx_roundtrip_template(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    tpl = maker.get("/api/v1/data/entities/kazna.balance/template.xlsx")
    assert tpl.status_code == 200 and "attachment" in tpl.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(tpl.content))
    assert wb.sheetnames == ["Данные", "Описание"]
    assert [c.value for c in wb["Данные"][1]] == ["branch_code", "bank_code", "date", "balance"]
    ws = wb["Данные"]
    ws.append([branch_code(1), BANK, "2026-09-30", 1500.5])
    ws.append([branch_code(1), BANK, datetime(2026, 8, 29), 3])  # noqa: DTZ001 -- openpyxl tz'siz sana yozadi
    buf = io.BytesIO()
    wb.save(buf)
    r = _post(maker, buf.getvalue(), XLSX, "t.xlsx")
    assert r.status_code == 201, r.text
    vals = migrator_sql("SELECT payload ->> 'date', payload ->> 'balance' "
                        "FROM core.manual_entry ORDER BY id")
    assert vals == [("2026-09-30", "1500.50"), ("2026-08-29", "3.00")]


def test_xlsx_zip_bomb_rejected(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/worksheets/sheet1.xml", b"\0" * (21 * 1024 * 1024))
    assert len(buf.getvalue()) < 1_048_576
    r = _post(maker, buf.getvalue(), XLSX)
    assert r.status_code == 422 and r.json()["error"]["code"] == "unsupported_file"
    many = io.BytesIO()
    with zipfile.ZipFile(many, "w") as zf:
        for i in range(101):
            zf.writestr(f"f{i}", b"x")
    assert _post(maker, many.getvalue(), XLSX).json()["error"]["code"] == "unsupported_file"
    assert _batches() == 0


@pytest.mark.parametrize("member", ["xl/vbaProject.bin", "xl/externalLinks/externalLink1.xml"])
def test_xlsx_macro_rejected(client_for, make_user: MakeUser, member: str) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    src = _xlsx([[branch_code(1), BANK, "2026-09-30", 1]])
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(src)) as zin, zipfile.ZipFile(buf, "w") as zout:
        for n in zin.namelist():
            zout.writestr(n, zin.read(n))
        zout.writestr(member, b"x")
    r = _post(maker, buf.getvalue(), XLSX)
    assert r.status_code == 422 and r.json()["error"]["code"] == "unsupported_file"
    assert _batches() == 0


def test_billion_laughs_rejected(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    src = _xlsx([[branch_code(1), BANK, "2026-09-30", 1]])
    lols = "".join(
        f'<!ENTITY lol{i} "{f"&lol{i - 1};" * 10}">' for i in range(1, 10))
    bomb = ('<?xml version="1.0"?><!DOCTYPE sst [<!ENTITY lol0 "lollollollol">' + lols + "]>"
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="1" '
            'uniqueCount="1"><si><t>&lol9;</t></si></sst>').encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(src)) as zin, zipfile.ZipFile(buf, "w") as zout:
        for n in zin.namelist():
            data = zin.read(n)
            if n == "[Content_Types].xml":  # openpyxl qismni faqat manifest orqali topadi
                data = data.replace(
                    b"</Types>",
                    b'<Override PartName="/xl/sharedStrings.xml" ContentType="application/'
                    b'vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/></Types>')
            zout.writestr(n, data)
        zout.writestr("xl/sharedStrings.xml", bomb)
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # KiB
    r = _post(maker, buf.getvalue(), XLSX)
    grown = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before
    assert r.status_code == 422 and r.json()["error"]["code"] == "unsupported_file"
    assert grown < 200 * 1024
    assert _batches() == 0


def test_formula_without_cache_rejected(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    body = _xlsx([[branch_code(1), BANK, "2026-09-30", "=1+1"]])  # openpyxl keshni yozmaydi
    r = _post(maker, body, XLSX)
    assert r.status_code == 422 and r.json()["error"]["code"] == "import_invalid"
    assert _codes(r)[0][2] == "formula_no_value"
    assert _batches() == 0


def test_wrong_content_type_422(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    for ctype in ("application/json", "text/plain", "application/octet-stream"):
        r = _post(maker, _csv(_row()), ctype)
        assert r.status_code == 422 and r.json()["error"]["code"] == "unsupported_file"
    assert _batches() == 0


def test_body_over_1mib_413(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    assert _post(maker, b"x" * (1_048_576 + 1)).status_code == 413


def test_import_rate_limited(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    codes = [_post(maker, _csv(_row(), head="x")).status_code for _ in range(11)]
    assert codes[:10] == [422] * 10 and codes[10] == 429


def test_branch_and_permission_scope(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    econ = client_for(make_user("economist_filiala", branch_ids=(2,)))
    r = _post(econ, _csv(_row()), url=URL.replace("branch_id=1", "branch_id=3"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "scope_violation"
    boss = client_for(make_user("nach_otdela"))  # faqat approve -- write yo'q
    assert _post(boss, _csv(_row())).status_code == 403
    assert boss.get("/api/v1/data/entities/kazna.balance/template.csv").status_code == 403
    assert _batches() == 0


def test_template_formula_injection_safe() -> None:
    assert imports._safe("=cmd|x") == "'=cmd|x"
    for ch in "=+-@":
        assert imports._safe(ch + "a") == "'" + ch + "a"
    assert imports._safe("balance") == "balance"
    raw = imports.template_csv(BALANCE)
    assert raw.startswith(b"\xef\xbb\xbf") and raw.decode("utf-8-sig").splitlines() == [HEAD]
    ws = load_workbook(io.BytesIO(imports.template_xlsx(BALANCE)))["Описание"]
    assert [c.value for c in ws[1]][:2] == ["Колонка", "Название"]
    assert not any(str(c.value).startswith(("=", "+", "@")) for row in ws.iter_rows() for c in row)


def test_template_csv_endpoint(client_for, make_user: MakeUser) -> None:  # type: ignore[no-untyped-def]
    maker = client_for(make_user("spec_kazna"))
    r = maker.get("/api/v1/data/entities/kazna.balance/template.csv")
    assert r.status_code == 200 and r.content.startswith(b"\xef\xbb\xbf")
    assert "attachment" in r.headers["content-disposition"]
