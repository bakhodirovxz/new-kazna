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

it('falls back to the section-level _page.tsx only where it exists', async () => {
  const resolve = createRegistry({
    './vvod/_page.tsx': () => Promise.resolve({ default: Demo }),
    './vvod/inbox.tsx': () => Promise.resolve({ default: () => <p>inbox</p> }),
  });
  const entity = resolve('vvod', 'kazna-balance');
  expect(entity).not.toBeNull();
  expect(resolve('vvod', 'kazna-payment_plan')).toBe(entity);
  expect(resolve('vvod', 'inbox')).not.toBe(entity);
  expect(resolve('kazna', 'kazna-balance')).toBeNull();
  expect(resolveSectionPage('vvod', 'kazna-balance')).not.toBeNull();
});
