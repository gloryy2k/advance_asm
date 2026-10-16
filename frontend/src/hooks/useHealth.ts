import { useEffect, useState } from "react";
import type { Health } from "../api/types";
import { useData } from "./useData";

/** The one place the pages read /api/health, refreshed when the tab regains focus (a tool installed meanwhile shows up). */
export function useHealth() {
  const [revision, setRevision] = useState(0);
  const health = useData<Health>("/api/health", revision);
  useEffect(() => {
    const refresh = () => document.visibilityState === "visible" && setRevision((v) => v + 1);
    document.addEventListener("visibilitychange", refresh);
    window.addEventListener("focus", refresh);
    return () => { document.removeEventListener("visibilitychange", refresh); window.removeEventListener("focus", refresh); };
  }, []);
  return health;
}
