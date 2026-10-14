export class ApiError extends Error {
  code: string;
  status: number;
  constructor(message: string, code = "", status = 0) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function request(path: string, options?: RequestInit) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(
      body.error?.message || `HTTP ${response.status}`,
      body.error?.code || "",
      response.status,
    );
  }
  return response;
}

export async function api<T = any>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await request(path, options);
  return response.headers.get("content-type")?.includes("application/json")
    ? response.json()
    : (response.text() as Promise<T>);
}

/** List endpoints report the unpaged size in X-Total-Count. */
export async function apiPage<T = any>(
  path: string,
  options?: RequestInit,
): Promise<{ items: T[]; total: number }> {
  const response = await request(path, options);
  const items: T[] = await response.json();
  const header = Number(response.headers.get("x-total-count"));
  return { items, total: Number.isFinite(header) && header > 0 ? header : items.length };
}
