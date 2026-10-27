import { describe, expect, it } from 'vitest';
import { inInset, insetXY, LABEL_SIDE, mainXY, markerRadius, UZ_GEO } from './geo';

describe('uz geo', () => {
  it('contains the prototype regions and inset', () => {
    expect(UZ_GEO.reg).toHaveLength(14);
    expect(UZ_GEO.reg.map((r) => r.n)).toContain('Ташкентская');
    expect(UZ_GEO.ins).toHaveLength(14);
    expect(UZ_GEO.inset).toHaveLength(4);
  });
  it('projects stations inside the canvas and the inset frame', () => {
    const [x, y] = mainXY(61.41, 41.24);
    expect(x).toBeGreaterThan(0);
    expect(x).toBeLessThan(UZ_GEO.W);
    expect(y).toBeGreaterThan(0);
    expect(y).toBeLessThan(UZ_GEO.H);
    expect(inInset(69.2797, 41.3111)).toBe(true);
    expect(inInset(61.41, 41.24)).toBe(false);
    const [ix, iy] = insetXY(70.029, 41.626);
    const [fx, fy, fw, fh] = UZ_GEO.inset;
    expect(ix).toBeGreaterThanOrEqual(fx);
    expect(ix).toBeLessThanOrEqual(fx + fw);
    expect(iy).toBeGreaterThanOrEqual(fy);
    expect(iy).toBeLessThanOrEqual(fy + fh);
  });
  it('sizes markers by capacity', () => {
    expect(markerRadius(666, false, false)).toBeGreaterThan(markerRadius(21, false, false));
    expect(markerRadius(null, true, true)).toBe(6);
    expect(LABEL_SIDE['UGE-02']).toBe('t');
  });
});
