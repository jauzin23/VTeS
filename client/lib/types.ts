export interface Heading {
  index: number;
  tag: string;
  level: number;
  text: string;
  outerHTML: string;
  xpath: string;
}

export interface Issue {
  rule: string;
  severity: "PASS" | "FAIL" | "REVIEW" | "INFO";
  message: string;
  element?: string;
  xpath?: string;
  details?: any;
}

export interface AspetResult {
  status: "ANALYZED" | "N/A" | "ERROR";
  issues: Issue[];
  message?: string;
}

export interface AuditResult {
  url: string;
  finalUrl: string;
  headings: Heading[];
  result: AspetResult;
  processedHtml?: string;
  auditadoEm: string;
  daCache?: boolean;
}

export interface SitemapPageResult {
  url: string;
  finalUrl: string;
  headings: Heading[];
  issues: Issue[];
  status: "ANALYZED" | "ERROR";
  issueCount: number;
  hasFailures: boolean;
  processedHtml?: string | null;
  error?: string;
}

export interface SitemapAuditResult {
  baseUrl: string;
  sitemapUrl: string;
  status: "completed" | "no_sitemap";
  message?: string;
  totalPages: number;
  totalIssues: number;
  pagesWithFailures: number;
  pagesWithWarnings?: number;
  pages: SitemapPageResult[];
  daCache?: boolean;
}

export interface CrawlerAuditResult {
  baseUrl: string;
  status: "completed" | "error";
  message?: string;
  totalPages: number;
  totalIssues: number;
  pagesWithFailures: number;
  pagesWithWarnings?: number;
  pages: SitemapPageResult[];
  daCache?: boolean;
}

export interface MultiUrlAuditGroup {
  inputUrl: string;
  pageCount: number;
  hasPagination: boolean;
  issueCount: number;
  pagesWithFailures: number;
  pagesWithWarnings?: number;
  pages: SitemapPageResult[];
}

export interface MultiUrlAuditResult {
  status: "completed";
  totalInputUrls: number;
  totalPages: number;
  totalIssues: number;
  pagesWithFailures: number;
  pagesWithWarnings?: number;
  groups: MultiUrlAuditGroup[];
  daCache?: boolean;
}

export interface HealthStatus {
  ok: boolean;
  queue: number;
  pending: number;
}
