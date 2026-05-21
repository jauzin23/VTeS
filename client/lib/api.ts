import type {
  AuditResult,
  HealthStatus,
  MultiUrlAuditResult,
  SitemapAuditResult,
  CrawlerAuditResult,
} from "./types";

export const getBaseUrl = (): string => {
  if (typeof window !== "undefined") {
    const hn = window.location.hostname;
    if (
      (hn === "localhost" || hn === "127.0.0.1" || hn.startsWith("192.168.")) &&
      window.location.port !== "3001"
    ) {
      return `http://${hn}:3001`;
    }
  }
  return "";
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getBaseUrl();
  const fullUrl = `${base}${path}`;

  const headers: Record<string, string> = {
    ...(init?.body ? { "Content-Type": "application/json" } : {}),
    ...(init?.headers as Record<string, string> || {}),
  };

  const res = await fetch(fullUrl, { ...init, headers });

  if (!res.ok) {
    let mensagem = `Erro ${res.status}`;
    try {
      const data = await res.json();
      if (data?.erro) mensagem = data.erro;
      else if (data?.detail) mensagem = data.detail;
    } catch {
      // ignore
    }
    throw new Error(mensagem);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<HealthStatus>("/api/health"),

  discover: (url: string) =>
    request<{ urls: string[] }>("/api/discover", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  audit: (url: string, force: boolean = false) =>
    request<AuditResult>("/api/audit", {
      method: "POST",
      body: JSON.stringify({ url, force }),
    }),

  sitemap: (url: string) =>
    request<SitemapAuditResult>("/api/sitemap", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  crawler: (url: string, maxPages: number = 100) =>
    request<CrawlerAuditResult>("/api/crawler", {
      method: "POST",
      body: JSON.stringify({ url, maxPages }),
    }),

  multiUrlAudit: (urls: string[]) =>
    request<MultiUrlAuditResult>("/api/multi-url-audit", {
      method: "POST",
      body: JSON.stringify({ urls }),
    }),
};
