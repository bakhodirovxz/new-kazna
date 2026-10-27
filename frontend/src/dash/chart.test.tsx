import { render, screen } from '@testing-library/react';
import type * as ChartJs from 'chart.js';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const created: unknown[] = [];
const destroy = vi.fn();
vi.mock('chart.js', async (importOriginal) => {
  const real = await importOriginal<typeof ChartJs>();
  class FakeChart {
    static register = vi.fn();
    canvas = { toBlob: (cb: (b: Blob | null) => void) => cb(new Blob(['png'], { type: 'image/png' })) };
    constructor(_ctx: unknown, config: unknown) {
      created.push(config);
    }
    destroy = destroy;
  }
  return { ...real, Chart: FakeChart };
});

import { barConfig, ChartCanvas, type ChartHandle } from './chart';

describe('ChartCanvas', () => {
  beforeEach(() => {
    created.length = 0;
    destroy.mockClear();
  });

  it('renders an accessible canvas with a fallback table and no chart without context', () => {
    render(
      <ChartCanvas
        config={barConfig({ labels: ['Янв'], series: [{ label: 'Поступления', data: [1], color: '#1d6df2' }] })}
        label="Поступления по месяцам"
        table={{ headers: ['Месяц', 'Поступления'], rows: [['Янв', 1]] }}
      />,
    );
    expect(screen.getByRole('img', { name: 'Поступления по месяцам' })).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Данные графика «Поступления по месяцам»' })).toBeInTheDocument();
    expect(created).toHaveLength(0);
  });

  it('creates the chart when a 2d context exists and exposes PNG export', async () => {
    const spy = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as never);
    const ref: { current: ChartHandle | null } = { current: null };
    const { unmount } = render(
      <ChartCanvas
        config={barConfig({ labels: ['Янв'], series: [{ label: 'A', data: [2], color: '#000' }], stacked: true })}
        label="A"
        table={{ headers: ['Месяц', 'A'], rows: [['Янв', 2]] }}
        chartRef={ref}
      />,
    );
    expect(created).toHaveLength(1);
    const blob = await ref.current?.toPng();
    expect(blob?.type).toBe('image/png');
    unmount();
    expect(destroy).toHaveBeenCalled();
    spy.mockRestore();
  });

  it('builds stacked bar configs with money tooltips', () => {
    const config = barConfig({ labels: ['Янв'], series: [{ label: 'A', data: [1500], color: '#000' }], stacked: true });
    expect(config.type).toBe('bar');
    const scales = config.options?.scales as Record<string, { stacked?: boolean }>;
    expect(scales.x?.stacked).toBe(true);
    expect(scales.y?.stacked).toBe(true);
  });
});

describe('ChartCanvas motion', () => {
  it('disables animation under prefers-reduced-motion', () => {
    const spy = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as never);
    const mm = vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true } as MediaQueryList);
    created.length = 0;
    render(<ChartCanvas config={barConfig({ labels: ['Янв'], series: [{ label: 'A', data: [1], color: '#000' }] })} label="A" table={{ headers: ['М'], rows: [['Янв']] }} />);
    expect((created[0] as { options: { animation: unknown } }).options.animation).toBe(false);
    mm.mockRestore();
    spy.mockRestore();
  });
});
