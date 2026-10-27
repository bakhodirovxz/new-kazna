import { render, screen } from '@testing-library/react';
import { Suspense } from 'react';
import { expect, it } from 'vitest';
import { createRegistry, resolveSectionPage, type SectionPageProps } from './registry';

function Demo({ section, page, filters }: SectionPageProps) {
  return (
    <p>
      {section}/{page}/{filters.per}
    </p>
  );
}

it('resolves pages by file name and returns null for missing pages', async () => {
  const resolve = createRegistry({ './kazna/svod.tsx': () => Promise.resolve({ default: Demo }) });
  expect(resolve('kazna', 'calendar')).toBeNull();
  const Page = resolve('kazna', 'svod');
  expect(Page).not.toBeNull();
  expect(resolve('kazna', 'svod')).toBe(Page);
  if (!Page) return;
  render(
    <Suspense fallback="...">
      <Page section="kazna" page="svod" filters={{ br: null, per: 'ytd' }} onBranch={() => undefined} />
    </Suspense>,
  );
  expect(await screen.findByText('kazna/svod/ytd')).toBeInTheDocument();
});

it('resolves the real S1 pages and nothing for pages not built yet', () => {
  expect(resolveSectionPage('obzor', 'svod')).not.toBeNull();
  expect(resolveSectionPage('kazna', 'celevye')).not.toBeNull();
  expect(resolveSectionPage('kredity', 'svod')).toBeNull();
});

it('ignores Object.prototype names', () => {
  expect(createRegistry({})('constructor', 'x')).toBeNull();
});
