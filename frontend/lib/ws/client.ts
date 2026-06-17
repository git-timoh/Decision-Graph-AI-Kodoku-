/** WebSocket client with exponential backoff and replay-on-reconnect.
 *
 * Per the design spec: on every (re)connect we first GET /events?since=<lastSeen>
 * and fold those in, then open the socket and resume. The reducer dedupes by
 * event id, so a small replay/live overlap is harmless. */
import type { WsEvent } from "@/lib/ws/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");

type Handlers = {
  apply: (event: WsEvent) => void;
  getSince: () => number;
  onConnected: (connected: boolean) => void;
};

export function connectSession(sessionId: string, h: Handlers): () => void {
  let closed = false;
  let ws: WebSocket | null = null;
  let backoff = 500;

  async function replay(): Promise<void> {
    try {
      const res = await fetch(
        `${API_BASE}/sessions/${sessionId}/events?since=${h.getSince()}`,
        { cache: "no-store" },
      );
      if (res.ok) (await res.json()).forEach(h.apply);
    } catch {
      /* network hiccup — the socket reconnect loop will retry */
    }
  }

  async function open(): Promise<void> {
    if (closed) return;
    await replay();
    if (closed) return;

    ws = new WebSocket(`${WS_BASE}/ws/sessions/${sessionId}`);
    ws.onopen = () => {
      backoff = 500;
      h.onConnected(true);
    };
    ws.onmessage = (e) => h.apply(JSON.parse(e.data) as WsEvent);
    ws.onerror = () => ws?.close();
    ws.onclose = () => {
      h.onConnected(false);
      if (closed) return;
      setTimeout(open, backoff);
      backoff = Math.min(backoff * 2, 10_000);
    };
  }

  void open();

  return () => {
    closed = true;
    ws?.close();
  };
}
