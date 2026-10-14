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
  | { page: "review"; id: string }
  | { page: "run"; id: string }
  | { page: "program"; slug: string; tab: string };

export const TABS = [
  "overview",
  "surface",
  "assets",
  "diff",
  "findings",
  "brief",
  "program",
] as const;

export function parseRoute(path: string): Route {
  const parts = path.split("?")[0].split("/").filter(Boolean);
  if (parts[0] === "new") return { page: "new" };
  if (parts[0] === "scan" && parts[1]) {
    return parts[2] === "review"
      ? { page: "review", id: parts[1] }
      : { page: "run", id: parts[1] };
  }
  if ((parts[0] === "program" || parts[0] === "target") && parts[1]) {
    const tab = (TABS as readonly string[]).includes(parts[2] || "")
      ? parts[2]
      : "overview";
    return { page: "program", slug: decodeURIComponent(parts[1]), tab };
  }
  return { page: "portfolio" };
}

export const programPath = (slug: string, tab = "overview") =>
  `/program/${encodeURIComponent(slug)}` + (tab === "overview" ? "" : `/${tab}`);
