import { useEffect, useState } from "react";
import { api } from "../api/client";
import { explain } from "../lib/errors";
import { TERMINAL } from "../lib/format";

/** GET `path`; with pollMs, repeat (retrying transient errors) until the scan is terminal. */
export function useData<T = any>(path: string | null, revision = 0, pollMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [code, setCode] = useState("");
  useEffect(() => {
    if (path === null) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    setData(null);
    setError("");
    setCode("");
    async function refresh() {
      let finished = false;
      try {
        const result = await api<T>(path as string, { signal: controller.signal });
        if (!live) return;
        setData(result);
        setError("");
        setCode("");
        finished = TERMINAL.has((result as any)?.status);
      } catch (e: any) {
        if (live) {
          setError(explain(e));
          setCode(e?.code || "");
        }
      } finally {
        if (live && pollMs && !finished) timer = setTimeout(refresh, pollMs);
      }
    }
    void refresh();
    return () => {
      live = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, [path, revision, pollMs]);
  return { data, error, code };
}
