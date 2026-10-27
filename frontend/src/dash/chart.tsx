import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
  type ChartConfiguration,
  type Plugin,
} from 'chart.js';
import { useEffect, useId, useRef, type MutableRefObject } from 'react';
import { t } from '../i18n';
import { cx } from '../ui/cx';
import type { CsvTable } from './csv';
import { formatMoney } from './money';
import './dash.css';

Chart.register(BarController, BarElement, CategoryScale, LinearScale, LineController, LineElement, PointElement, Tooltip);

export type AnyChartConfig = ChartConfiguration<'bar' | 'line', number[], string | string[]>;

export interface ChartHandle {
  toPng(): Promise<Blob | null>;
}

export interface Series {
  label: string;
  data: number[];
  color: string;
  type?: 'bar' | 'line';
  /** Reja chizig'i kabi — uzuk-uzuk, nuqtasiz (prototip genCard). */
  dashed?: boolean;
}

export function cssColor(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/** Prototip ranglari (dash.css tokenlari; test/print'da fallback). */
export const COLORS = {
  in: () => cssColor('--in', '#1d6df2'),
  out: () => cssColor('--out', '#9dc0e8'),
  bal: () => cssColor('--bal', '#0b4fa8'),
  prev: () => cssColor('--prev', '#c3d7ee'),
  v0: () => cssColor('--v0', '#0b4fa8'),
  v1: () => cssColor('--v1', '#2f8ef5'),
  v2: () => cssColor('--v2', '#5fd0e0'),
};

// PNG oq fonda bo'lsin (shaffof emas).
const whiteBackground: Plugin<'bar' | 'line'> = {
  id: 'ugkWhiteBackground',
  beforeDraw(chart) {
    const { ctx, width, height } = chart;
    ctx.save();
    ctx.globalCompositeOperation = 'destination-over';
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, width, height);
    ctx.restore();
  },
};

export function barConfig({
  labels,
  series,
  stacked = false,
  format = formatMoney,
}: {
  labels: Array<string | string[]>;
  series: Series[];
  stacked?: boolean;
  format?: (value: number, digits: number) => string;
}): AnyChartConfig {
  return {
    type: 'bar',
    data: {
      labels,
      datasets: series.map((s) =>
        s.type === 'line'
          ? { type: 'line' as const, label: s.label, data: s.data, borderColor: s.color, backgroundColor: s.color, borderWidth: s.dashed ? 2 : 3, borderDash: s.dashed ? [6, 5] : [], pointRadius: s.dashed ? 0 : 3, tension: 0.25, order: 0 }
          : { type: 'bar' as const, label: s.label, data: s.data, backgroundColor: s.color, borderRadius: 3, maxBarThickness: 36, order: 1 },
      ),
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (item) => `${item.dataset.label ?? ''}: ${format(item.parsed.y, 2)}` } },
      },
      scales: {
        x: { stacked, grid: { display: false } },
        y: { stacked, beginAtZero: true, ticks: { maxTicksLimit: 6, callback: (value) => format(Number(value), 0) } },
      },
    },
    plugins: [whiteBackground],
  };
}

export interface ChartCanvasProps {
  config: AnyChartConfig;
  label: string;
  table: CsvTable;
  size?: 'md' | 'sm';
  chartRef?: MutableRefObject<ChartHandle | null>;
  format?: (value: number, digits: number) => string;
}

export function ChartCanvas({ config, label, table, size = 'md', chartRef, format = formatMoney }: ChartCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const tableId = useId();

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return undefined;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    const chart = new Chart(context, { ...config, options: { ...config.options, animation: reduce ? false : config.options?.animation } });
    if (chartRef) {
      chartRef.current = {
        toPng: () => new Promise<Blob | null>((resolve) => chart.canvas.toBlob((blob) => resolve(blob), 'image/png')),
      };
    }
    return () => {
      chart.destroy();
      if (chartRef) chartRef.current = null;
    };
  }, [config, chartRef]);

  return (
    <div className={cx('cv', size === 'sm' && 'cv--sm')}>
      <canvas ref={canvasRef} role="img" aria-label={label} aria-describedby={tableId} />
      <table id={tableId} className="visually-hidden" aria-label={t('dash.dataTable', { title: label })}>
          <thead>
            <tr>
              {table.headers.map((h, i) => (
                <th key={i} scope="col">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i}>
                {row.map((value, j) => (
                <td key={j}>{typeof value === 'number' ? format(value, 2) : value}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
