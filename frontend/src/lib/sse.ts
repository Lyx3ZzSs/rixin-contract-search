import type { StreamEvent } from './types';

interface SubscribeOptions {
  taskId: string;
  onEvent: (event: StreamEvent) => void;
  onError: (error: Error) => void;
  onComplete: () => void;
}

const terminalEvents = new Set(['task_completed', 'task_failed']);

export function subscribeTaskEvents({ taskId, onEvent, onError, onComplete }: SubscribeOptions): () => void {
  const controller = new AbortController();
  void readTaskEvents(taskId, controller.signal, onEvent, onComplete).catch((error) => {
    if (!controller.signal.aborted) onError(error instanceof Error ? error : new Error(String(error)));
  });
  return () => controller.abort();
}

async function readTaskEvents(taskId: string, signal: AbortSignal, onEvent: (event: StreamEvent) => void, onComplete: () => void): Promise<void> {
  const response = await fetch(`/api/screening-tasks/${encodeURIComponent(taskId)}/events`, { signal });
  if (!response.ok || !response.body) {
    throw new Error(`Unable to subscribe task events: HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const event = parseFrame(frame);
      if (event) {
        onEvent(event);
        if (terminalEvents.has(event.type)) {
          onComplete();
          return;
        }
      }
      boundary = buffer.indexOf('\n\n');
    }
  }
}

function parseFrame(frame: string): StreamEvent | null {
  const trimmed = frame.trim();
  if (!trimmed || trimmed.startsWith(':')) return null;
  const dataLine = trimmed.split('\n').find((line) => line.startsWith('data:'));
  if (!dataLine) return null;
  return JSON.parse(dataLine.slice(5).trim()) as StreamEvent;
}
