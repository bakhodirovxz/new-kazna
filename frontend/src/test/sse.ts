import type { MockResponse } from './mockApi';

export interface SseController {
  stream: ReadableStream<Uint8Array>;
  send(event: string, data: unknown): void;
  close(): void;
  cancelled(): boolean;
}

/** Test boshqaradigan SSE oqimi: hodisalar `send` bilan, oxiri — `close`; klient bekor qilsa `cancelled()`. */
export function sseController(): SseController {
  const encoder = new TextEncoder();
  let controller: ReadableStreamDefaultController<Uint8Array> | null = null;
  let wasCancelled = false;
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
    cancel() {
      wasCancelled = true;
    },
  });
  return {
    stream,
    send(event, data) {
      controller?.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
    },
    close() {
      controller?.close();
    },
    cancelled: () => wasCancelled,
  };
}

export function sseResponse(ctrl: SseController): MockResponse {
  return { status: 200, raw: ctrl.stream, headers: { 'Content-Type': 'text/event-stream' } };
}
