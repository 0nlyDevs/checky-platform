"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { io, type Socket } from "socket.io-client";
import { API_URL, getApiToken } from "@/lib/api";

// Payload shapes are per event; each handler annotates its own.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Handlers = { [event: string]: ((payload: any) => void) | undefined };

/**
 * Joins the workspace room and forwards server events. Reconnects on its own;
 * `reconnected` fires after each reconnection so callers can refetch what they missed.
 */
export function useWorkspaceSocket(workspaceId: string | undefined, handlers: Handlers) {
  const [online, setOnline] = useState(true);
  const handlersRef = useRef(handlers);
  useLayoutEffect(() => {
    handlersRef.current = handlers;
  });

  useEffect(() => {
    if (!workspaceId) return;
    let firstConnect = true;
    const socket: Socket = io(API_URL, {
      transports: ["websocket"],
      // A fresh token on every (re)connection, since they expire after 15 minutes.
      auth: (cb) => {
        getApiToken().then((token) => cb({ token }), () => cb({}));
      },
    });

    socket.on("connect", () => {
      setOnline(true);
      socket.emit("join", workspaceId);
      if (!firstConnect) handlersRef.current.reconnected?.(undefined);
      firstConnect = false;
    });
    socket.on("disconnect", () => setOnline(false));
    socket.on("connect_error", () => setOnline(false));
    socket.onAny((event: string, payload: unknown) => {
      const fn = handlersRef.current[event];
      if (event !== "reconnected" && fn) fn(payload);
    });
    return () => {
      socket.disconnect();
    };
  }, [workspaceId]);

  return { online };
}
