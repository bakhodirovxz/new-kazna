import { describe, expect, it } from 'vitest';
import { buildHash, parseHash } from './hash';

describe('scenario in section routes', () => {
  it('parses a known scenario and keeps old routes unchanged', () => {
    expect(parseHash('#finmodel/dolg?br=2&scen=water')).toEqual({ kind: 'section', section: 'finmodel', page: 'dolg', br: 2, per: null, scen: 'water' });
    expect(parseHash('#finmodel/svod?scen=evil')).toEqual({ kind: 'section', section: 'finmodel', page: 'svod', br: null, per: null });
    expect(parseHash('#kazna/svod?per=q1')).toEqual({ kind: 'section', section: 'kazna', page: 'svod', br: null, per: 'q1' });
  });

  it('builds the scenario after branch and period', () => {
    expect(buildHash({ kind: 'section', section: 'finmodel', page: 'svod', br: 3, per: 'm08', scen: 'fx' })).toBe('#finmodel/svod?br=3&per=m08&scen=fx');
    expect(buildHash({ kind: 'section', section: 'finmodel', page: 'svod', br: null, per: null, scen: null })).toBe('#finmodel/svod');
  });
});
