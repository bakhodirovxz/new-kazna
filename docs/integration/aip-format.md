# Адресная инвестиционная программа (АИП): формат файлов — UGEKAZNA

Источник АИП — канонические CSV-файлы файлового коннектора (решение S4: без прямой интеграции
с модулем adreska). Файлы готовит ПТО/отдел инвестиций или выгрузка из adreska по таблице ниже.
Правила — как для остальных файлов: UTF-8, `;`, даты `ГГГГ-ММ-ДД`, суммы — млн сум с точкой.

## dim_source.csv, dim_object.csv

```
code;name;kind
SRC-1;Бюджетные средства на капитальные вложения;budget
```
`kind`: `budget`, `ifi` (МФИ), `bank`, `own`.

```
code;name;program_code;work_type;commissioning_year;total_cost;source_code
OBJ-01;Модернизация гидроагрегатов Чарвакской ГЭС;АИП-2028-01;modernization;2028;2400000.00;SRC-1
```
`work_type`: `new`, `reconstruction`, `modernization`; `total_cost` — общая стоимость, млн сум.

## fact_investment.csv — объект × месяц

```
doc_type;src_id;date;branch_code;object_code;source_code;plan;fact;physical_pct;advance;advance_date_id
aip_opening;OPEN-01;2025-01-01;UGE-02;OBJ-01;SRC-1;0;300.00;;0;
aip_month;INV-01-202608;2026-08-01;UGE-02;OBJ-01;SRC-1;60.00;40.00;0.4000;30.00;20260601
```
- `date` — первое число месяца; план указывается на все месяцы года, включая будущие.
- `plan` — график финансирования месяца; `fact` — профинансировано (освоено) за месяц.
- `physical_pct` — выполнено по КС-2 нарастающим итогом / сметная стоимость, доля 0…1; пусто —
  без изменений (берётся последнее значение).
- `advance` — остаток незакрытого аванса на конец месяца; `advance_date_id` — дата выдачи самого
  раннего незакрытого аванса (ГГГГММДД).
- `aip_opening` — одна строка на объект: профинансировано до начала истории (входит в «освоено
  ранее», в помесячный факт не входит).

## fact_object_stage.csv — этапы

```
doc_type;src_id;date;branch_code;object_code;stage_no;stage_name;fact_date_id
aip_stage;STG-01-1;2026-03-15;UGE-02;OBJ-01;1;Проектно-сметная документация;20260310
```
`date` — плановое окончание этапа, `fact_date_id` — фактическое (ГГГГММДД, пусто — не завершён).

## Соответствие полям модуля adreska

| Каноническая колонка | adreska |
|---|---|
| `dim_object.code`, `name` | `projects.project_code`, `project_name` |
| `work_type` | `project_type`: `yangi_qurilish` → `new`, `rekonstruksiya` → `reconstruction`, `modernizatsiya` → `modernization` |
| `commissioning_year` | год `projects.end_date` |
| `total_cost` | `projects.total_budget` (сум → млн сум) |
| `source_code` / `dim_source.kind` | `financing_sources.source_type`: `davlat_byudjeti` → `budget`, `xorij_krediti` → `ifi`, `bank_krediti` → `bank`, `oz_mablagi`, `grant`, `investor` → `own` |
| `branch_code` | `projects.branch_id` → `branches.code` (сопоставить с кодами UGE-xx) |
| `plan` | `budget_limits` (месячные; квартальные и годовые — равными долями по месяцам) |
| `fact` | `payments.payment_amount` по месяцу `payment_date` |
| `advance`, `advance_date_id` | `payments` с `payment_type = avans` за вычетом зачтённых (зачёт авансов в adreska не ведётся — рассчитывается при выгрузке) |
| `physical_pct` | `work_forms` (КС-2) нарастающим итогом / `total_budget` (или `completion_pct`) |
| `fact_object_stage` | `project_stages`: `stage_kind`, `planned_end`, `actual_end` |

Не выгружаются (персональные данные, ТЗ раздел 9): `responsible_person`, `chief_engineer`,
`signed_by`, `contractor_tin` физических лиц.
