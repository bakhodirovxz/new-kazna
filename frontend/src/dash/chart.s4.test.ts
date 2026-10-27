import { describe, expect, it } from 'vitest';
import { barConfig } from './chart';

describe('barConfig right axis', () => {
  it('puts series marked axis right on y1 and adds the axis only when needed', () => {
    const cfg = barConfig({
      labels: ['Янв'],
      series: [{ label: 'ФОТ', data: [180], color: '#1d6df2' }, { label: 'Средняя', data: [2], color: '#0b4fa8', type: 'line', axis: 'right' }],
      rightFormat: (v) => `${v} млн`,
    });
    expect(cfg.options?.scales?.y1).toBeDefined();
    expect((cfg.data.datasets[1] as { yAxisID?: string }).yAxisID).toBe('y1');
    expect((cfg.data.datasets[0] as { yAxisID?: string }).yAxisID).toBe('y');
    const plain = barConfig({ labels: ['Янв'], series: [{ label: 'ФОТ', data: [180], color: '#1d6df2' }] });
    expect(plain.options?.scales?.y1).toBeUndefined();
  });
});
