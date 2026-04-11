import { useEffect, useEffectEvent, useRef, useState } from "react";

export function useWebSocket<T>(url: string, onMessage: (payload: T) => void) {
  const [connected, setConnected] = useState(false);
  const reconnectTimer = useRef<number | null>(null);

  const handleMessage = useEffectEvent((payload: T) => {
    onMessage(payload);
  });

  useEffect(() => {
    let socket: WebSocket | null = null;
    let cancelled = false;

    const connect = () => {
      if (cancelled) {
        return;
      }

      socket = new WebSocket(url);
      socket.onopen = () => {
        setConnected(true);
        socket?.send("ping");
      };
      socket.onmessage = (event) => {
        handleMessage(JSON.parse(event.data) as T);
      };
      socket.onclose = () => {
        setConnected(false);
        if (!cancelled) {
          reconnectTimer.current = window.setTimeout(connect, 2000);
        }
      };
      socket.onerror = () => {
        socket?.close();
      };
    };

    connect();

    return () => {
      cancelled = true;
      setConnected(false);
      if (reconnectTimer.current) {
        window.clearTimeout(reconnectTimer.current);
      }
      socket?.close();
    };
  }, [url]);

  return { connected };
}
