import { useEffect, useState } from "react";

export const go = (path: string) => {
  location.hash = path;
};

export const currentPath = () => location.hash.slice(1) || "/";

export function useHashPath() {
  const [path, setPath] = useState(currentPath());
  useEffect(() => {
    const update = () => setPath(currentPath());
    window.addEventListener("hashchange", update);
    update();
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return path;
}

export type Route =
  | { page: "portfolio" }
  | { page: "new" }
  | { page: "help" }
  | { page: "profiles" }
  | { page: "tools"; focus: string }
  | { page: "review"; id: string }
  | { page: "run"; id: string }
  | { page: "program"; slug: string; tab: string; view: string };

/** Five areas instead of seven tabs. Old links (surface, assets, diff, brief, program) still resolve. */
export const TABS = ["overview", "data", "findings", "history", "guide"] as const;
const LEGACY: Record<string, { tab: string; view?: string }> = {
  surface: { tab: "data", view: "surface" },
  assets: { tab: "data", view: "hosts" },
  urls: { tab: "data", view: "urls" },
  diff: { tab: "history", view: "diff" },
  brief: { tab: "guide", view: "brief" },
  program: { tab: "guide", view: "instructions" },
};

export function parseRoute(path: string): Route {
  const [clean, query = ""] = path.split("?");
  const parts = clean.split("/").filter(Boolean);
  const params = new URLSearchParams(query);
  if (parts[0] === "new") return { page: "new" };
  if (parts[0] === "help") return { page: "help" };
  if (parts[0] === "profiles") return { page: "profiles" };
  if (parts[0] === "tools") return { page: "tools", focus: params.get("focus") || "" };
  if (parts[0] === "scan" && parts[1]) {
    return parts[2] === "review" ? { page: "review", id: parts[1] } : { page: "run", id: parts[1] };
  }
  if ((parts[0] === "program" || parts[0] === "target") && parts[1]) {
    const raw = parts[2] || "overview";
    const legacy = LEGACY[raw];
    const tab = legacy ? legacy.tab : (TABS as readonly string[]).includes(raw) ? raw : "overview";
    return { page: "program", slug: decodeURIComponent(parts[1]), tab, view: params.get("v") || legacy?.view || "" };
  }
  return { page: "portfolio" };
}

export const programPath = (slug: string, tab = "overview", view = "") =>
  `/program/${encodeURIComponent(slug)}` + (tab === "overview" ? "" : `/${tab}`) + (view ? `?v=${view}` : "");

/** Query string of the current hash route, e.g. #/program/x/data?v=urls&tag=api -> {v, tag}. */
export const routeParams = (path = currentPath()) => new URLSearchParams(path.split("?")[1] || "");

/** Preserve the selected completed scan when opening a result from Run. */
export function dataLink(slug: string, view: { kind: string; filter?: Record<string, string> }, scan?: string | number): string {
  const q = new URLSearchParams(view.filter || {});
  if (scan !== undefined) q.set("scan", String(scan));
  if (view.kind === "findings") return `#${programPath(slug, "findings")}${q.toString() ? "?" + q : ""}`;
  const v = view.kind === "urls" ? "urls" : "hosts";
  q.set("v", v);
  return `#/program/${encodeURIComponent(slug)}/data?${q}`;
}
