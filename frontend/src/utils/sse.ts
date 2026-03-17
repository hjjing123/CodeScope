import { getAuthToken } from './authToken';

export interface SseEventPayload {
  id?: string;
  event: string;
  data: unknown;
}

export interface OpenSseStreamOptions {
  url: string;
  signal: AbortSignal;
  onEvent: (payload: SseEventPayload) => void;
  method?: 'GET' | 'POST';
  body?: string;
  headers?: Record<string, string>;
}

const parseChunk = (chunk: string): SseEventPayload | null => {
  const lines = chunk.split(/\r?\n/);
  let id = '';
  let event = 'message';
  const dataLines: string[] = [];

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (!line || line.startsWith(':')) {
      continue;
    }
    if (line.startsWith('id:')) {
      id = line.slice(3).trim();
      continue;
    }
    if (line.startsWith('event:')) {
      event = line.slice(6).trim() || 'message';
      continue;
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  const rawData = dataLines.join('\n');
  let data: unknown = rawData;
  try {
    data = JSON.parse(rawData);
  } catch {
    data = rawData;
  }
  return { id: id || undefined, event, data };
};

export const openSseStream = async ({
  url,
  signal,
  onEvent,
  method = 'GET',
  body,
  headers,
}: OpenSseStreamOptions) => {
  const token = getAuthToken();
  const response = await fetch(url, {
    method,
    headers: {
      Accept: 'text/event-stream',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    credentials: 'same-origin',
    signal,
    body,
  });

  if (!response.ok || !response.body) {
    const contentType = response.headers.get('content-type') || '';
    let errorMessage = `SSE request failed: ${response.status}`;

    try {
      if (contentType.includes('application/json')) {
        const payload = await response.json();
        const message = payload?.error?.message || payload?.message;
        if (typeof message === 'string' && message.trim()) {
          errorMessage = message;
        }
      } else {
        const text = await response.text();
        if (text.trim()) {
          errorMessage = text.trim();
        }
      }
    } catch {
      // ignore parse failures and fall back to status-based message
    }

    throw new Error(errorMessage);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (!signal.aborted) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    while (true) {
      const boundary = buffer.indexOf('\n\n');
      if (boundary < 0) {
        break;
      }
      const chunk = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const payload = parseChunk(chunk);
      if (payload) {
        onEvent(payload);
      }
    }
  }
};
