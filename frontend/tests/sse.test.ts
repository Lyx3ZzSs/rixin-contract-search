import { afterEach, describe, expect, it, vi } from 'vitest';
import { subscribeTaskEvents } from '../src/lib/sse';
import type { StreamEvent } from '../src/lib/types';

function streamResponse(frames: string[]): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const frame of frames) controller.enqueue(encoder.encode(frame));
        controller.close();
      }
    }),
    { status: 200 }
  );
}

describe('subscribeTaskEvents', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('ignores keepalive comment frames and completes on terminal events', async () => {
    const events: StreamEvent[] = [];
    const onComplete = vi.fn();
    const onError = vi.fn();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          ': keepalive\n\n',
          'id: task-1:1\nevent: progress\ndata: {"event_id":"task-1:1","type":"progress","task_id":"task-1","timestamp":"2026-06-22T00:00:00Z","payload":{"progress_percent":50}}\n\n',
          ': keepalive\n\n',
          'id: task-1:2\nevent: task_completed\ndata: {"event_id":"task-1:2","type":"task_completed","task_id":"task-1","timestamp":"2026-06-22T00:00:01Z","payload":{"included_count":1}}\n\n'
        ])
      )
    );

    subscribeTaskEvents({
      taskId: 'task-1',
      onEvent(event) {
        events.push(event);
      },
      onError,
      onComplete
    });

    await vi.waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    expect(onError).not.toHaveBeenCalled();
    expect(events.map((event) => event.type)).toEqual(['progress', 'task_completed']);
  });

  it('encodes reserved characters in the task events URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      streamResponse([
        'id: task-1:1\nevent: task_completed\ndata: {"event_id":"task-1:1","type":"task_completed","task_id":"task-1/with?query#hash","timestamp":"2026-06-22T00:00:01Z","payload":{}}\n\n'
      ])
    );
    const onComplete = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    subscribeTaskEvents({
      taskId: 'task-1/with?query#hash',
      onEvent() {},
      onError() {},
      onComplete
    });

    await vi.waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks/task-1%2Fwith%3Fquery%23hash/events', {
      signal: expect.any(AbortSignal)
    });
  });
});
