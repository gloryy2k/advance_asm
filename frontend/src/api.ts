export async function api<T = any>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error?.message || `HTTP ${response.status}`);
  }
  return response.headers.get("content-type")?.includes("application/json")
    ? response.json()
    : (response.text() as Promise<T>);
}
export const go = (path: string) => {
  location.hash = path;
};
export type Config = {
  depth: "passive" | "light" | "strong";
  threads: number;
  rate_limit: number;
  scan_timeout: number;
  nuclei_severity: string;
  skip_nmap: boolean;
  skip_nuclei: boolean;
  skip_active_crawl: boolean;
  categories_enabled: string[];
  excluded_hosts: string[];
};
