import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  build: {
    target: 'es2022',
    sourcemap: false,
    // CSP: font-src/img-src 'self' — shrift va rasmlar data: URI bo'lib qolmasin.
    assetsInlineLimit: 0,
    modulePreload: { polyfill: false },
  },
  test: {
    environment: 'jsdom',
    environmentOptions: { jsdom: { url: 'https://ugk.test/' } },
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: { include: [/tokens\.css/, /display\.css/, /shell\.css/] }, // ?raw faqat CSS-ishlov yoqilgan faylda matn qaytaradi (tokens.test.ts)
    restoreMocks: true,
    unstubGlobals: true,
  },
});
