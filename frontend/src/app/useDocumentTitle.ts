import { useEffect } from 'react';

export function useDocumentTitle(title: string | null): void {
  useEffect(() => {
    document.title = title ? `${title} | UGEKAZNA` : 'UGEKAZNA';
  }, [title]);
}
