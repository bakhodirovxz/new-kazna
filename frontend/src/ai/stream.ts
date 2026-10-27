import { ApiError, apiUrl, backgroundHeaders, CSRF_COOKIE, CSRF_HEADER, readCookie, toApiError } from '../api/client';
import { t } from '../i18n';

export type AiEvent =
  | { type: 'start'; requestId: number }
  | { type: 'delta'; text: string }
  | { type: 'done'; length: number }
  | { type: 'error'; code: string; message: string };

export interface AiRequestBody {
  section: string;
  page: string;
  br: number | null;
  per: string;
  scen?: string;
  preset?: string;
  question?: string;
}

/** Bitta SSE freymi (`event:` + `data:` qatorlari). Izoh yoki noma'lum hodisa — `null`. */
export function parseFrame(frame: string): AiEvent | null {
  let name = '';
  let data = '';
  for (const line of frame.split('\n')) {
    if (line.startsWith('event: ')) name = line.slice(7).trim();
    else if (line.startsWith('data: ')) data += line.slice(6);
  }
  if (!name || !data) return null;
  const payload = JSON.parse(data) as Record<string, unknown>;
  switch (name) {
    case 'start':
      return { type: 'start', requestId: Number(payload.request_id) };
    case 'delta':
      return { type: 'delta', text: String(payload.text ?? '') };
    case 'done':
      return { type: 'done', length: Number(payload.length ?? 0) };
    case 'error':
      return { type: 'error', code: String(payload.code ?? 'ai_failed'), message: String(payload.message ?? '') };
    default:
      return null;
  }
}

/** TZ 7: javob oqim bilan (POST + SSE — EventSource POST/CSRF qo'llamaydi). Bekor qilish — `signal`. */
export async function streamAnalysis(body: AiRequestBody, onEvent: (event: AiEvent) => void, signal: AbortSignal): Promise<void> {
  const headers: Record<string, string> = { Accept: 'text/event-stream', 'Content-Type': 'application/json', ...backgroundHeaders() };
  const token = readCookie(CSRF_COOKIE);
  if (token) headers[CSRF_HEADER] = token;
  let response: Response;
  try {
    response = await fetch(apiUrl('/ai/analyze'), { method: 'POST', headers, body: JSON.stringify(body), credentials: 'same-origin', signal });
  } catch (error) {
    if ((error as { name?: string } | null)?.name === 'AbortError') throw error;
    throw new ApiError(0, 'network', t('error.network'));
  }
  if (!response.ok || response.body === null) {
    const payload: unknown = await response.json().catch(() => null);
    throw toApiError(response, payload);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const onAbort = () => {
    void reader.cancel();
  };
  signal.addEventListener('abort', onAbort);
  let buffer = '';
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let end = buffer.indexOf('\n\n');
      while (end >= 0) {
        const event = parseFrame(buffer.slice(0, end));
        buffer = buffer.slice(end + 2);
        if (event) onEvent(event);
        end = buffer.indexOf('\n\n');
      }
    }
  } finally {
    signal.removeEventListener('abort', onAbort);
  }
}
