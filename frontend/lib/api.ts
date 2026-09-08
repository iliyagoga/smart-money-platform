import { token } from "./auth";

const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8050";

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const accessToken = await token();
  const response = await fetch(baseUrl + path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      ...init.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail ? `${response.status}: ${detail}` : `Сервис вернул ошибку ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const getWebSocketUrl = () => `${baseUrl.replace(/^http/, "ws")}/ws`;

export async function downloadApi(path: string): Promise<Blob> {
  const response = await fetch(baseUrl + path, {
    headers: { Authorization: `Bearer ${await token()}` },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return response.blob();
}
