import { useEffect, useRef, useState } from "react";

/**
 * Live scan log over WebSocket with replay cursor + reconnect. The scan *status* never
 * depends on this: the page polls REST separately, so a broken WebSocket cannot hang the UI.
 */
export function useScanStream(id: string, finished = false, onDone?: () => void) {
  const finishedRef = useRef(finished);
  finishedRef.current = finished;
  const doneRef = useRef(onDone);
  doneRef.current = onDone;
  const [events, setEvents] = useState<any[]>([]);
  const [connection, setConnection] = useState("Đang kết nối");
  useEffect(() => {
    let stopped = false,
      after = 0,
      done = false,
      ws: WebSocket | undefined;
    let timer: ReturnType<typeof setTimeout>;
    setEvents([]);
    function connect() {
      if (stopped) return;
      ws = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/scan/${id}?after=${after}`,
      );
      ws.onopen = () => setConnection("Live");
      ws.onmessage = (e) => {
        const event = JSON.parse(e.data);
        after = Math.max(after, event.id || 0);
        setEvents((list) => [...list, event].slice(-1500));
        if (event.type === "done") {
          done = true;
          setConnection("Đã kết thúc");
          doneRef.current?.();
        }
      };
      ws.onclose = () => {
        if (!stopped && !done && !finishedRef.current) {
          setConnection("Mất kết nối — đang thử lại");
          timer = setTimeout(() => {
            if (!finishedRef.current) connect();
          }, 1500);
        }
      };
      ws.onerror = () => ws?.close();
    }
    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, [id]);
  return { events, connection };
}
