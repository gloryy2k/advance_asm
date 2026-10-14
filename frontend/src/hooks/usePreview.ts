import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Preview } from "../api/types";
import { explain } from "../lib/errors";

/** Debounced, race-safe call to /api/scope/preview (pure parse; nothing is stored). */
export function usePreview(body: object | null, delay = 300) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const key = body ? JSON.stringify(body) : "";
  useEffect(() => {
    if (!key) {
      setPreview(null);
      setPending(false);
      setError("");
      return;
    }
    setPending(true);
    let live = true;
    const timer = setTimeout(async () => {
      try {
        const result = await api<Preview>("/api/scope/preview", { method: "POST", body: key });
        if (live) {
          setPreview(result);
          setError("");
        }
      } catch (e) {
        if (live) setError(explain(e));
      } finally {
        if (live) setPending(false);
      }
    }, delay);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [key, delay]);
  return { preview, pending, error };
}
