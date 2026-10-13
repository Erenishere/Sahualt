const backendBaseUrl =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:5272";

export function backendAssetUrl(path: string): string {
  return `${backendBaseUrl}${path}`;
}

export class BackendRequestError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function backendRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${backendBaseUrl}${path}`, {
    ...init,
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as { title?: string } | null;
    throw new BackendRequestError(response.status, problem?.title ?? `Request failed (${response.status}).`);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export async function backendGet<T>(path: string): Promise<T> {
  return backendRequest<T>(path);
}

export async function backendPost<T>(path: string, body?: object): Promise<T> {
  return backendRequest<T>(path, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
}

export async function backendPut<T>(path: string, body: object): Promise<T> {
  return backendRequest<T>(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function backendPostForm<T>(path: string, body: FormData): Promise<T> {
  return backendRequest<T>(path, { method: "POST", body });
}
