# Кадры: формат файла численности — UGEKAZNA

Пока HR API не даёт разреза по организациям (запрос — `docs/integration/hr-sorov-s4.md`),
численность загружается CSV-файлами файлового коннектора. Только агрегаты: ФИО, ПИНФЛ, табельные
номера и другие персональные данные в файлы не включаются (ТЗ, раздел 9).

## dim_position.csv — категории персонала

```
code;category;department
POS-3;Оперативный персонал;Производственные подразделения
```

## fact_hr.csv — филиал × категория × месяц

```
doc_type;src_id;date;branch_code;pos_code;headcount_plan;headcount_fact;payroll;hired;fired;overtime_hours
hr_month;HR-UGE-02-3-202608;2026-08-31;UGE-02;POS-3;90;81;0;2;3;400.0
```
- `date` — последний день месяца (текущий месяц — дата выгрузки); `headcount_plan` — штат,
  `headcount_fact` — фактическая численность на дату; `hired`, `fired` — принято и уволено за
  месяц; `overtime_hours` — часы сверхурочной работы за месяц.
- `payroll` — 0: фонд оплаты труда берётся из платежей по статьям зарплаты (настройка
  `kazna.calendar_kinds`, ключ `salary`).
