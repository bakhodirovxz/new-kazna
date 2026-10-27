/** Brauzerda faylni saqlash (blob: URL — CSP'da navigatsiya, connect-src emas). */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function safeFileName(title: string): string {
  return title.replace(/[\\/:*?"<>|«»]+/g, '').trim().replace(/\s+/g, '_').slice(0, 80) || 'export';
}
