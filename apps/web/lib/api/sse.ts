/**
 * POST + Server-Sent Events. `EventSource` only supports GET, so we read the response body as
 * a stream and parse `event:`/`data:` frames ourselves. Same-origin via the /api proxy, so the
 * session cookie rides along.
 */

import { ApiError, type ApiErrorBody } from "@/lib/api/client";

export interface StreamOptions<E> {
  body: unknown;
  onEvent: (event: E) => void;
  signal?: AbortSignal;
}

export async function streamPost<E extends { type: string }>(path: string, { body, onEvent, signal }: StreamOptions<E>): Promise<void> {
  const response = await fetch(`/api/v1${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    let json: ApiErrorBody | null = null;
    try {
      json = (await response.json()) as ApiErrorBody;
    } catch {
      // non-JSON error body
    }
    throw new ApiError(
      response.status,
      json?.error ?? { code: "HTTP_ERROR", message: "The request could not be completed.", details: {} },
    );
  }
  if (!response.body) throw new ApiError(502, { code: "NO_STREAM", message: "The server sent no stream.", details: {} });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flush = (frame: string) => {
    let data = "";
    for (const line of frame.split("\n")) {
      if (line.startsWith("data:")) data += line.slice(5).trimStart();
    }
    if (!data) return;
    try {
      onEvent(JSON.parse(data) as E);
    } catch {
      // malformed frame: skip rather than kill the stream
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      flush(buffer.slice(0, idx));
      buffer = buffer.slice(idx + 2);
    }
  }
  if (buffer.trim()) flush(buffer);
}
