import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach, vi } from 'vitest';
import { installMatchMedia, resetViewport } from './viewport';

installMatchMedia();

beforeEach(() => {
  resetViewport();
  window.history.replaceState(null, '', '/');
  document.cookie = '__Host-ugk_csrf=; Max-Age=0; Secure; Path=/';
  document.getElementById('root')?.removeAttribute('inert');
  document.body.classList.remove('no-scroll');
  Element.prototype.scrollIntoView = vi.fn();
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
  window.print = vi.fn();
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
  URL.createObjectURL = vi.fn(() => 'blob:ugk-test');
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
});

// jsdom'da canvas yo'q: ChartCanvas kontekst olmasa grafikni yaratmaydi (fallback jadval qoladi).
Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', { value: () => null, writable: true, configurable: true });
