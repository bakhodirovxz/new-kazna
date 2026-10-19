import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { App } from './App';

it('renders the application root', () => {
  render(<App />);
  expect(screen.getByRole('heading', { name: 'UGEKAZNA' })).toBeInTheDocument();
});
