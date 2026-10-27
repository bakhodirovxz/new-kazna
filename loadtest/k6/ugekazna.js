// UGEKAZNA yuklama testi (TZ 9; spec 6.5, 9): sahifa ochish va filtr almashtirish p95.
// Sessiyalar oldindan yaratiladi (python -m app.devtools seed-load) — har VU o'z foydalanuvchisi.
// Ketma-ket ssenariylar: 20, 50, 100 VU (har biri DURATION, oralig'i 30 s). Normalar 20 va 50 VU uchun.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Trend } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'https://caddy';
const DURATION = __ENV.DURATION || '3m';
const sessions = new SharedArray('sessions', () => JSON.parse(open(__ENV.SESSIONS_FILE || '/work/sessions.json')));
const endpoints = JSON.parse(open('./endpoints.json'));
const PERIODS = ['ytd', 'q1', 'q2', 'q3', 'm01', 'm02', 'm03', 'm04', 'm05', 'm06', 'm07', 'm08'];

const pageLoad = new Trend('page_load', true);
const filterChange = new Trend('filter_change', true);

function seconds(value) {
  const match = /^(\d+)(s|m)$/.exec(value);
  if (!match) {
    throw new Error(`DURATION formati 30s yoki 3m bo'lishi kerak, berilgan: ${value}`);
  }
  return Number(match[1]) * (match[2] === 'm' ? 60 : 1);
}

const STEP = seconds(DURATION) + 30;

export const options = {
  scenarios: {
    vu20: { executor: 'constant-vus', vus: 20, duration: DURATION, startTime: '0s' },
    vu50: { executor: 'constant-vus', vus: 50, duration: DURATION, startTime: `${STEP}s` },
    vu100: { executor: 'constant-vus', vus: 100, duration: DURATION, startTime: `${2 * STEP}s` },
  },
  thresholds: {
    'page_load{scenario:vu20}': ['p(95)<2000'],
    'filter_change{scenario:vu20}': ['p(95)<1000'],
    'page_load{scenario:vu50}': ['p(95)<2000'],
    'filter_change{scenario:vu50}': ['p(95)<1000'],
    // 100 VU — hisobiy cho'qqi: submetrika hisobotga chiqishi uchun, amalda cheklamaydi.
    'page_load{scenario:vu100}': ['p(95)<600000'],
    'filter_change{scenario:vu100}': ['p(95)<600000'],
    // Bosqich bo'yicha xato ulushi va so'rovlar soni hisobotga chiqishi uchun submetrikalar.
    'http_req_failed{scenario:vu20}': ['rate<0.01'],
    'http_req_failed{scenario:vu50}': ['rate<0.01'],
    'http_req_failed{scenario:vu100}': ['rate<1.01'],
    'http_reqs{scenario:vu20}': ['count>=0'],
    'http_reqs{scenario:vu50}': ['count>=0'],
    'http_reqs{scenario:vu100}': ['count>=0'],
    // Xato/check normalari ham faqat 20 va 50 VU bosqichlariga (global metrikaga 100 VU ham kirardi).
    'checks{scenario:vu20}': ['rate>0.99'],
    'checks{scenario:vu50}': ['rate>0.99'],
  },
};

const etags = {};

function fill(path, session) {
  const branch = session.branches.length > 0
    ? session.branches[0]
    : 1 + Math.floor(Math.random() * 16);
  const period = PERIODS[Math.floor(Math.random() * PERIODS.length)];
  return path.replace('{br}', String(branch)).replace('{per}', period);
}

function batch(paths, session, trend) {
  const urls = paths.map((path) => BASE + fill(path, session));
  const requests = urls.map((url) => {
    const headers = {};
    if (etags[url]) {
      headers['If-None-Match'] = etags[url];
    }
    return ['GET', url, null, {
      cookies: { '__Host-ugk_session': session.token },
      headers,
      tags: { name: url.split('?')[0].replace(BASE, '') },
    }];
  });
  const started = Date.now();
  const responses = http.batch(requests);
  trend.add(Date.now() - started);
  responses.forEach((response, index) => {
    check(response, { 'status 200/304': (r) => r.status === 200 || r.status === 304 });
    const etag = response.headers.Etag;
    if (etag) {
      etags[urls[index]] = etag;
    }
  });
}

export default function () {
  const session = sessions[(__VU - 1) % sessions.length];
  batch(endpoints.page, session, pageLoad);
  sleep(1 + Math.random() * 2);
  for (let i = 0; i < 3; i += 1) {
    batch(endpoints.filter, session, filterChange);
    sleep(1 + Math.random() * 2);
  }
}

function p95(data, metric) {
  const item = data.metrics[metric];
  if (!item || !item.values || item.values['p(95)'] === undefined) {
    return null;
  }
  return Math.round(item.values['p(95)']);
}

export function handleSummary(data) {
  const rows = ['vu20', 'vu50', 'vu100'].map((scenario) => {
    const page = p95(data, `page_load{scenario:${scenario}}`);
    const filter = p95(data, `filter_change{scenario:${scenario}}`);
    const failedItem = data.metrics[`http_req_failed{scenario:${scenario}}`];
    const checksItem = data.metrics[`checks{scenario:${scenario}}`];
    // Итог = те же нормы, что и thresholds: p95 + ошибки < 1 % + checks > 99 % на ступени.
    const ok = page !== null && filter !== null && page < 2000 && filter < 1000
      && failedItem !== undefined && failedItem.values.rate < 0.01
      && checksItem !== undefined && checksItem.values.rate > 0.99;
    let verdict = 'справочно';
    if (scenario !== 'vu100') {
      verdict = ok ? 'соответствует' : 'НЕ соответствует';
    }
    const show = (value) => (value === null ? '—' : String(value));
    const reqs = data.metrics[`http_reqs{scenario:${scenario}}`];
    const errors = failedItem ? (failedItem.values.rate * 100).toFixed(2) : '—';
    const rps = reqs ? (reqs.values.count / seconds(DURATION)).toFixed(1) : '—';
    return `| ${scenario.slice(2)} | ${show(page)} | ${show(filter)} | ${errors} | ${rps} | ${verdict} |`;
  });
  const failed = data.metrics.http_req_failed
    ? (data.metrics.http_req_failed.values.rate * 100).toFixed(2)
    : '—';
  const report = [
    '# Протокол нагрузочного теста UGEKAZNA',
    '',
    `Дата (UTC): ${new Date().toISOString()}; стенд: ${BASE}; длительность ступени: ${DURATION}.`,
    `Стенд: ${__ENV.LOAD_LABEL || 'не указан (UGK_LOAD_LABEL)'}.`,
    'Норматив (ТЗ, раздел 9): открытие страницы ≤ 2000 мс, смена фильтра ≤ 1000 мс (p95) при 20 и 50 пользователях; 100 — расчётный пик (справочно).',
    '',
    '| Пользователей | Страница p95, мс | Фильтр p95, мс | Ошибки, % | RPS | Итог |',
    '|---|---|---|---|---|---|',
    ...rows,
    '',
    `Доля ошибочных запросов: ${failed} %.`,
    '',
  ].join('\n');
  return {
    '/work/summary.json': JSON.stringify(data, null, 2),
    '/work/report.md': report,
    stdout: report,
  };
}
