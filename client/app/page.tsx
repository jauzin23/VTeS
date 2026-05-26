"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import {
  Loader2,
  Search,
  Globe,
  FileText,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  AlertCircle,
  Map,
  XCircle,
  ZoomIn,
  ZoomOut,
  Eye,
  Clock,
} from "lucide-react";
import { toast } from "sonner";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { DiaTextReveal } from "@/components/ui/dia-text-reveal";
import { MorphingText } from "@/components/ui/morphing-text";
import { PreviewBrowserFrame } from "@/components/preview-browser-frame";
import { api } from "@/lib/api";
import type {
  AuditResult,
  Issue,
  Heading,
  MultiUrlAuditResult,
  SitemapAuditResult,
  SitemapPageResult,
  CrawlerAuditResult,
} from "@/lib/types";

// ─── Severity Badge ──────────────────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: Issue["severity"] }) {
  if (severity === "PASS")
    return (
      <Badge className="bg-emerald-500 hover:bg-emerald-600 text-white shrink-0">
        PASS
      </Badge>
    );
  if (severity === "FAIL")
    return (
      <Badge variant="destructive" className="shrink-0">
        FAIL
      </Badge>
    );
  if (severity === "REVIEW")
    return (
      <Badge className="bg-amber-500 hover:bg-amber-600 text-white shrink-0">
        REVIEW
      </Badge>
    );
  return (
    <Badge variant="outline" className="shrink-0">
      {severity}
    </Badge>
  );
}

// ─── Heading Tree ─────────────────────────────────────────────────────────────

const LEVEL_COLORS: Record<number, string> = {
  1: "text-violet-700 font-bold",
  2: "text-blue-700 font-semibold",
  3: "text-sky-700",
  4: "text-teal-700",
  5: "text-green-700",
  6: "text-gray-500",
};

function HeadingTree({
  headings,
  onSelect,
  selectedIndex,
  compact = false,
}: {
  headings: Heading[];
  onSelect?: (index: number, xpath: string, text: string) => void;
  selectedIndex?: number | null;
  compact?: boolean;
}) {
  if (!headings || headings.length === 0)
    return (
      <p className="text-sm text-muted-foreground italic">
        Nenhum cabeçalho encontrado.
      </p>
    );

  return (
    <div className="flex flex-col gap-0">
      {headings.map((h, i) => {
        const isSelected = selectedIndex === h.index;
        return (
          <button
            key={i}
            onClick={() => onSelect?.(h.index, h.xpath || "", h.text || "")}
            className={`w-full flex items-start gap-2 text-left transition-colors rounded px-1 py-1 border-b last:border-b-0 ${
              isSelected
                ? "bg-amber-50 border-l-2 border-l-amber-400"
                : onSelect
                  ? "hover:bg-muted/50 cursor-pointer"
                  : "cursor-default"
            }`}
            style={{ paddingLeft: `${(h.level - 1) * 14 + 4}px` }}
            disabled={!onSelect}
          >
            <span
              className={`text-xs font-mono w-6 shrink-0 pt-0.5 ${
                LEVEL_COLORS[h.level] ?? "text-gray-600"
              }`}
            >
              H{h.level}
            </span>
            <span
              className={`text-sm text-foreground leading-tight break-words min-w-0 ${
                compact ? "text-xs" : ""
              }`}
            >
              {h.text || (
                <em className="text-muted-foreground">&lt;vazio&gt;</em>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// ─── helpers ──────────────────────────────────────────────────────────────────

/** Extract visible text from an HTML snippet (e.g. '<div class="x">Avisos</div>' → 'Avisos'). */
function extractText(html?: string): string {
  if (!html) return "";
  return html.replace(/<[^>]*>/g, "").trim();
}

// ─── Issue List ───────────────────────────────────────────────────────────────

function IssueList({
  issues,
  onHighlight,
}: {
  issues: Issue[];
  onHighlight?: (xpath: string, text: string) => void;
}) {
  if (!issues || issues.length === 0)
    return (
      <div className="flex items-center gap-2 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-700">
        <CheckCircle2 className="size-4 shrink-0" />
        <span className="text-sm font-medium">Sem problemas detectados</span>
      </div>
    );

  return (
    <div className="space-y-2">
      {issues.map((issue, idx) => {
        const canHighlight = !!(onHighlight && (issue.xpath || issue.element));
        return (
          <div
            key={idx}
            className={`border rounded-lg p-3 space-y-1.5 text-sm bg-white ${
              canHighlight
                ? "cursor-pointer hover:border-amber-400 hover:bg-amber-50/30 transition-colors"
                : ""
            }`}
            onClick={() => {
              if (canHighlight)
                onHighlight!(issue.xpath ?? "", extractText(issue.element));
            }}
            title={canHighlight ? "Clique para destacar na página" : undefined}
          >
            <div className="flex justify-between items-start gap-3">
              <span className="font-medium leading-snug text-foreground">
                [{issue.rule}] {issue.message}
              </span>
              <SeverityBadge severity={issue.severity} />
            </div>
            {issue.element && (
              <pre className="bg-muted/60 p-2 rounded text-xs overflow-x-auto text-muted-foreground border font-mono">
                {issue.element}
              </pre>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Single Page Audit ────────────────────────────────────────────────────────

function SinglePageAudit() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AuditResult | null>(null);
  const [selectedHeading, setSelectedHeading] = useState<number | null>(null);
  const [zoom, setZoom] = useState(0.6);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Listen for heading-clicked messages coming from inside the iframe
  useEffect(() => {
    function onMsg(e: MessageEvent) {
      if (e.data?.type === "heading-clicked") {
        setSelectedHeading(e.data.index);
      }
    }
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  function sendToIframe(msg: object) {
    iframeRef.current?.contentWindow?.postMessage(msg, "*");
  }

  function handleSelectHeading(index: number, xpath: string, text: string) {
    setSelectedHeading(index);
    sendToIframe({ type: "select-heading", index, xpath, text });
  }

  function handleHighlightXPath(xpath: string, text?: string) {
    sendToIframe({ type: "highlight-xpath", xpath, text });
  }

  async function handleAudit(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setResult(null);
    setSelectedHeading(null);
    const toastId = toast.loading("A auditar cabeçalhos...", {
      description: url,
    });

    try {
      const res = await api.audit(url.trim());
      setResult(res);
      const failCount = res.result.issues.filter(
        (i) => i.severity === "FAIL",
      ).length;
      if (failCount === 0) {
        toast.success("Auditoria concluída - sem falhas!", { id: toastId });
      } else {
        toast.warning(`Auditoria concluída - ${failCount} problema(s)`, {
          id: toastId,
        });
      }
    } catch (err: any) {
      toast.error("Falha ao auditar", {
        id: toastId,
        description: err.message,
      });
    } finally {
      setLoading(false);
    }
  }

  const failCount =
    result?.result.issues.filter((i) => i.severity === "FAIL").length ?? 0;
  const reviewCount =
    result?.result.issues.filter((i) => i.severity === "REVIEW").length ?? 0;
  const firstHighlightableIssue = result?.result.issues.find(
    (issue) => issue.xpath,
  );

  return (
    <div className="space-y-6">
      {/* Input */}
      <Card className="shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <FileText className="size-4 text-primary" />
            Auditar Página
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleAudit}
            className="flex flex-col sm:flex-row gap-3"
          >
            <Input
              id="single-page-url"
              type="url"
              placeholder="https://exemplo.com/pagina"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={loading}
              className="flex-1"
              required
            />
            <Button
              type="submit"
              disabled={loading}
              className="w-full sm:w-auto"
            >
              {loading ? (
                <Loader2 className="size-4 animate-spin mr-2" />
              ) : (
                <Search className="size-4 mr-2" />
              )}
              Auditar
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Loading */}
      {loading && (
        <div className="flex flex-col items-center justify-center p-16 border rounded-xl bg-muted/30 text-muted-foreground">
          <Loader2 className="size-8 animate-spin mb-4 text-primary" />
          <p className="font-medium">A analisar cabeçalhos...</p>
          <p className="text-xs mt-1 opacity-70">{url}</p>
        </div>
      )}

      {/* Empty */}
      {!loading && !result && (
        <Card className="border-dashed py-16 flex flex-col items-center justify-center text-center">
          <FileText className="size-12 text-muted-foreground mb-4 opacity-40" />
          <CardTitle className="text-base font-semibold">
            Pronto para auditar
          </CardTitle>
          <CardDescription className="max-w-sm mt-2 text-sm">
            Insira um URL acima para verificar a hierarquia de cabeçalhos H1–H6
            da página.
          </CardDescription>
        </Card>
      )}

      {/* Results: two-column layout */}
      {!loading && result && (
        <div className="space-y-4">
          {/* Summary strip */}
          <div className="grid grid-cols-3 gap-3">
            <div className="border rounded-lg p-3 text-center bg-white shadow-sm">
              <p className="text-xs text-muted-foreground mb-1">Cabeçalhos</p>
              <p className="text-2xl font-bold text-foreground">
                {result.headings.length}
              </p>
            </div>
            <div
              className={`border rounded-lg p-3 text-center shadow-sm ${
                failCount > 0 ? "bg-red-50 border-red-200" : "bg-white"
              }`}
            >
              <p className="text-xs text-muted-foreground mb-1">Falhas</p>
              <p
                className={`text-2xl font-bold ${
                  failCount > 0 ? "text-red-600" : "text-foreground"
                }`}
              >
                {failCount}
              </p>
            </div>
            <div
              className={`border rounded-lg p-3 text-center shadow-sm ${
                reviewCount > 0 ? "bg-amber-50 border-amber-200" : "bg-white"
              }`}
            >
              <p className="text-xs text-muted-foreground mb-1">Revisão</p>
              <p
                className={`text-2xl font-bold ${
                  reviewCount > 0 ? "text-amber-600" : "text-foreground"
                }`}
              >
                {reviewCount}
              </p>
            </div>
          </div>

          {/* Main two-column: left panel + iframe */}
          <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
            {/* Left panel */}
            <div className="xl:col-span-4 space-y-4">
              {/* Issues */}
              <Card className="shadow-sm">
                <CardHeader className="pb-2 border-b bg-muted/30 py-3">
                  <CardTitle className="text-sm">
                    Problemas Detectados
                  </CardTitle>
                  {result.result.issues.length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      Clique num problema para o destacar na página →
                    </p>
                  )}
                </CardHeader>
                <CardContent className="p-3 max-h-64 overflow-y-auto">
                  <IssueList
                    issues={result.result.issues}
                    onHighlight={handleHighlightXPath}
                  />
                </CardContent>
              </Card>

              {/* Heading tree */}
              <Card className="shadow-sm">
                <CardHeader className="pb-2 border-b bg-muted/30 py-3">
                  <CardTitle className="text-sm">
                    Árvore de Cabeçalhos ({result.headings.length})
                  </CardTitle>
                  {result.headings.length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      Clique num cabeçalho para navegar na página →
                    </p>
                  )}
                </CardHeader>
                <CardContent className="p-2 max-h-80 overflow-y-auto">
                  <HeadingTree
                    headings={result.headings}
                    onSelect={handleSelectHeading}
                    selectedIndex={selectedHeading}
                  />
                </CardContent>
              </Card>

              {result.daCache && (
                <p className="text-xs text-muted-foreground text-center italic">
                  Resultado da cache · auditado em{" "}
                  {new Date(result.auditadoEm).toLocaleString("pt-PT")}
                </p>
              )}
            </div>

            {/* Iframe panel */}
            <Card className="xl:col-span-8 overflow-hidden border-slate-200/80 shadow-sm">
              <CardHeader className="flex flex-row items-center justify-between border-b bg-muted/30 p-3">
                <div className="min-w-0">
                  <CardTitle className="text-sm">Pré-visualização</CardTitle>
                  {result.finalUrl && (
                    <p className="text-xs text-muted-foreground truncate max-w-xs">
                      {result.finalUrl}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 rounded-full border bg-background px-3 py-1.5 shrink-0">
                  <span className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
                    Zoom
                  </span>
                  <span className="w-10 text-center font-mono text-xs">
                    {Math.round(zoom * 100)}%
                  </span>
                </div>
              </CardHeader>
              <CardContent className="space-y-4 bg-[linear-gradient(180deg,rgba(248,250,252,0.96),rgba(241,245,249,0.88))] p-4 md:p-5">
                {result.processedHtml ? (
                  <>
                    <div className="overflow-hidden rounded-[1.75rem] border border-slate-200/80 bg-white/70 p-3 shadow-[0_18px_70px_rgba(15,23,42,0.14)]">
                      <PreviewBrowserFrame url={result.finalUrl}>
                        <div className="h-[700px] w-full overflow-auto bg-slate-100">
                          <iframe
                            ref={iframeRef}
                            srcDoc={result.processedHtml}
                            className="border-0 bg-white"
                            style={{
                              width: `${100 / zoom}%`,
                              height: `${100 / zoom}%`,
                              transform: `scale(${zoom})`,
                              transformOrigin: "top left",
                            }}
                            sandbox="allow-scripts allow-popups allow-forms"
                            title="Page preview"
                          />
                        </div>
                      </PreviewBrowserFrame>
                    </div>
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                      <div className="text-xs text-muted-foreground">
                        Navegue por cabeçalhos, destaque falhas e ajuste o zoom
                        sem sair da auditoria.
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-8"
                          onClick={() =>
                            setZoom((z) =>
                              Math.max(0.25, +(z - 0.1).toFixed(2)),
                            )
                          }
                        >
                          <ZoomOut className="mr-1.5 size-3.5" />
                          Reduzir
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-8"
                          onClick={() =>
                            setZoom((z) => Math.min(1.5, +(z + 0.1).toFixed(2)))
                          }
                        >
                          <ZoomIn className="mr-1.5 size-3.5" />
                          Aumentar
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-8"
                          onClick={() => setZoom(0.6)}
                        >
                          Repor zoom
                        </Button>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="flex h-[700px] w-full items-center justify-center rounded-[1.5rem] border border-dashed bg-white/70 text-sm text-muted-foreground">
                    Pré-visualização não disponível.
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Sitemap Audit ────────────────────────────────────────────────────────────

function SitemapPageRow({
  page,
  index,
}: {
  page: SitemapPageResult;
  index: number;
}) {
  const [open, setOpen] = useState(false);
  const [selectedHeading, setSelectedHeading] = useState<number | null>(null);
  const [zoom, setZoom] = useState(0.45);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const hasError = page.status === "ERROR";

  const failCount =
    page.issues?.filter((i) => i.severity === "FAIL").length ?? 0;
  const reviewCount =
    page.issues?.filter((i) => i.severity === "REVIEW").length ?? 0;

  const sendToIframe = useCallback((msg: object) => {
    iframeRef.current?.contentWindow?.postMessage(msg, "*");
  }, []);

  function handleSelectHeading(idx: number, xpath: string, text: string) {
    setSelectedHeading(idx);
    sendToIframe({ type: "select-heading", index: idx, xpath, text });
  }

  function handleHighlightXPath(xpath: string, text: string) {
    sendToIframe({ type: "highlight-xpath", xpath, text });
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button
          className={`w-full flex items-center gap-3 px-4 py-3 text-left border-b last:border-b-0 hover:bg-muted/30 transition-colors ${
            hasError
              ? "bg-red-50/50"
              : failCount > 0
                ? "bg-red-50/20"
                : reviewCount > 0
                  ? "bg-amber-50/30"
                  : ""
          }`}
        >
          <span className="text-xs text-muted-foreground w-7 text-right shrink-0">
            {index + 1}
          </span>
          <div className="flex-1 min-w-0">
            <a
              href={page.url}
              target="_blank"
              rel="noreferrer"
              className="text-sm font-medium text-foreground hover:text-primary hover:underline truncate block"
              onClick={(e) => e.stopPropagation()}
            >
              {page.url}
            </a>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {hasError ? (
              <Badge
                variant="outline"
                className="text-red-600 border-red-200 bg-red-50 text-xs"
              >
                Erro
              </Badge>
            ) : failCount > 0 ? (
              <Badge variant="destructive" className="text-xs">
                {failCount} falha{failCount !== 1 ? "s" : ""}
              </Badge>
            ) : reviewCount > 0 ? (
              <Badge className="bg-amber-500 hover:bg-amber-600 text-white text-xs">
                {reviewCount} aviso{reviewCount !== 1 ? "s" : ""}
              </Badge>
            ) : (
              <Badge className="bg-emerald-500 hover:bg-emerald-600 text-white text-xs">
                OK
              </Badge>
            )}
            <span className="text-muted-foreground">
              {open ? (
                <ChevronDown className="size-4" />
              ) : (
                <ChevronRight className="size-4" />
              )}
            </span>
          </div>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="bg-muted/10 border-b px-4 py-4 space-y-4">
          {hasError ? (
            <div className="flex items-center gap-2 text-red-600 text-sm">
              <XCircle className="size-4 shrink-0" />
              <span>{page.error ?? "Erro desconhecido"}</span>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
              {/* Left column (Problems, Headings, timestamp) */}
              <div className="lg:col-span-5 space-y-4">
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                    Problemas
                  </h4>
                  <div className="max-h-[220px] overflow-y-auto border rounded-lg bg-white p-2">
                    <IssueList
                      issues={page.issues}
                      onHighlight={
                        page.processedHtml ? handleHighlightXPath : undefined
                      }
                    />
                  </div>
                </div>

                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                    Árvore de Cabeçalhos ({page.headings.length})
                  </h4>
                  <div className="max-h-[260px] overflow-y-auto border rounded-lg p-2 bg-white">
                    <HeadingTree
                      headings={page.headings}
                      compact
                      onSelect={
                        page.processedHtml ? handleSelectHeading : undefined
                      }
                      selectedIndex={selectedHeading}
                    />
                  </div>
                </div>

                {page.auditadoEm && (
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-2 bg-white border rounded-md px-2 py-1.5 shadow-sm w-fit">
                    <Clock className="size-3.5 text-muted-foreground shrink-0" />
                    <span>
                      Auditado em:{" "}
                      {new Date(page.auditadoEm).toLocaleString("pt-PT")}
                    </span>
                  </div>
                )}
              </div>

              {/* Right column (Iframe preview) */}
              <div className="lg:col-span-7">
                {page.processedHtml ? (
                  <Card className="shadow-sm overflow-hidden">
                    <CardHeader className="border-b bg-muted/30 p-2.5 flex flex-row items-center justify-between">
                      <div className="min-w-0 flex-1 mr-2">
                        <p className="text-xs font-medium">Pré-visualização</p>
                        <p
                          className="text-xs text-muted-foreground truncate"
                          title={page.finalUrl}
                        >
                          {page.finalUrl}
                        </p>
                      </div>
                      <div className="flex items-center gap-1 bg-background border rounded-md px-2 py-1 shrink-0">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5"
                          onClick={() => setZoom((z) => Math.max(0.2, z - 0.1))}
                          title="Reduzir zoom"
                        >
                          <ZoomOut className="size-2.5" />
                        </Button>
                        <span className="text-xs font-mono w-9 text-center">
                          {Math.round(zoom * 100)}%
                        </span>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5"
                          onClick={() => setZoom((z) => Math.min(1.2, z + 0.1))}
                          title="Aumentar zoom"
                        >
                          <ZoomIn className="size-2.5" />
                        </Button>
                      </div>
                    </CardHeader>
                    <CardContent className="p-0 bg-gray-100 h-[500px] relative overflow-hidden">
                      <div className="w-full h-full overflow-auto">
                        <iframe
                          ref={iframeRef}
                          srcDoc={page.processedHtml}
                          className="border-0 bg-white"
                          style={{
                            width: `${100 / zoom}%`,
                            height: `${100 / zoom}%`,
                            transform: `scale(${zoom})`,
                            transformOrigin: "top left",
                          }}
                          sandbox="allow-scripts allow-popups allow-forms"
                          title={`Preview ${page.url}`}
                        />
                      </div>
                    </CardContent>
                  </Card>
                ) : (
                  <div className="border rounded-lg bg-muted/20 p-8 text-center text-xs text-muted-foreground h-[500px] flex items-center justify-center">
                    Sem pré-visualização disponível
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function SitemapAudit() {
  const [domain, setDomain] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SitemapAuditResult | null>(null);
  const [filter, setFilter] = useState<"all" | "fail" | "warn" | "ok">("all");

  async function handleSitemap(e: React.FormEvent) {
    e.preventDefault();
    if (!domain.trim()) return;

    setLoading(true);
    setResult(null);
    const toastId = toast.loading("A processar sitemap...", {
      description: domain,
    });

    try {
      const res = await api.sitemap(domain.trim());
      setResult(res);
      if (res.status === "no_sitemap") {
        toast.error("Sitemap não encontrado", {
          id: toastId,
          description: res.message,
        });
      } else {
        toast.success(`Auditoria concluída - ${res.totalPages} página(s)`, {
          id: toastId,
          description: `${res.pagesWithFailures} com falhas`,
        });
      }
    } catch (err: any) {
      toast.error("Falha no audit de sitemap", {
        id: toastId,
        description: err.message,
      });
    } finally {
      setLoading(false);
    }
  }

  const filteredPages =
    result?.pages.filter((p) => {
      const failCount =
        p.issues?.filter((i) => i.severity === "FAIL").length ?? 0;
      const reviewCount =
        p.issues?.filter((i) => i.severity === "REVIEW").length ?? 0;
      if (filter === "fail") return p.status === "ERROR" || failCount > 0;
      if (filter === "warn")
        return p.status !== "ERROR" && failCount === 0 && reviewCount > 0;
      if (filter === "ok")
        return p.status !== "ERROR" && failCount === 0 && reviewCount === 0;
      return true;
    }) ?? [];

  return (
    <div className="space-y-6">
      {/* Input */}
      <Card className="shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Map className="size-4 text-primary" />
            Auditar por Sitemap
          </CardTitle>
          <CardDescription>
            Insira o domínio (ex:{" "}
            <code className="bg-muted px-1 rounded text-xs">exemplo.com</code>)
            - o sistema irá buscar o{" "}
            <code className="bg-muted px-1 rounded text-xs">/sitemap.xml</code>,
            descobrir todas as páginas incluindo paginação, e auditar os
            cabeçalhos de cada uma.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleSitemap}
            className="flex flex-col sm:flex-row gap-3"
          >
            <Input
              id="sitemap-domain-input"
              type="text"
              placeholder="exemplo.com ou https://exemplo.com"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              disabled={loading}
              className="flex-1"
              required
            />
            <Button
              type="submit"
              disabled={loading}
              className="w-full sm:w-auto"
            >
              {loading ? (
                <Loader2 className="size-4 animate-spin mr-2" />
              ) : (
                <Globe className="size-4 mr-2" />
              )}
              Analisar Sitemap
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Loading */}
      {loading && (
        <div className="flex flex-col items-center justify-center p-16 border rounded-xl bg-muted/30 text-muted-foreground">
          <Loader2 className="size-8 animate-spin mb-4 text-primary" />
          <p className="font-medium">
            A processar sitemap e auditar páginas...
          </p>
          <p className="text-xs mt-1 opacity-70">
            Isto pode demorar alguns minutos dependendo do número de páginas.
          </p>
        </div>
      )}

      {/* Empty */}
      {!loading && !result && (
        <Card className="border-dashed py-16 flex flex-col items-center justify-center text-center">
          <Map className="size-12 text-muted-foreground mb-4 opacity-40" />
          <CardTitle className="text-base font-semibold">
            Auditoria por Sitemap
          </CardTitle>
          <CardDescription className="max-w-sm mt-2 text-sm">
            Insira um domínio acima para auditar automaticamente todas as
            páginas do seu sitemap.
          </CardDescription>
        </Card>
      )}

      {/* No sitemap */}
      {!loading && result?.status === "no_sitemap" && (
        <div className="flex items-center gap-3 p-4 border border-amber-200 bg-amber-50 rounded-lg text-amber-700">
          <AlertCircle className="size-5 shrink-0" />
          <div className="space-y-3">
            <p className="font-medium text-sm">Sitemap não encontrado</p>
            <p className="text-xs mt-0.5">{result.message}</p>
            <a
              href={result.sitemapUrl}
              target="_blank"
              rel="noreferrer"
              className="text-xs underline hover:text-amber-900 mt-1 inline-block"
            >
              {result.sitemapUrl}
            </a>
          </div>
        </div>
      )}

      {/* Results */}
      {!loading && result && result.status === "completed" && (
        <div className="space-y-4">
          {/* Timing details */}
          {(result.iniciadoEm || result.duracaoFormatada) && (
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2 bg-slate-50 border rounded-lg text-xs text-slate-500">
              {result.iniciadoEm && (
                <div className="flex items-center gap-1.5">
                  <Clock className="size-3.5 text-slate-400" />
                  <span>
                    <strong>Início:</strong>{" "}
                    {new Date(result.iniciadoEm).toLocaleString("pt-PT")}
                  </span>
                </div>
              )}
              {result.finalizadoEm && (
                <div className="flex items-center gap-1.5">
                  <Clock className="size-3.5 text-slate-400" />
                  <span>
                    <strong>Fim:</strong>{" "}
                    {new Date(result.finalizadoEm).toLocaleString("pt-PT")}
                  </span>
                </div>
              )}
              {result.duracaoFormatada && (
                <div className="flex items-center gap-1.5">
                  <Clock className="size-3.5 text-primary" />
                  <span>
                    <strong>Tempo decorrido:</strong> {result.duracaoFormatada}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Summary */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <div className="border rounded-lg p-3 text-center bg-white shadow-sm">
              <p className="text-xs text-muted-foreground mb-1">
                Páginas auditadas
              </p>
              <p className="text-2xl font-bold text-foreground">
                {result.totalPages}
              </p>
            </div>
            <div className="border rounded-lg p-3 text-center bg-white shadow-sm">
              <p className="text-xs text-muted-foreground mb-1">
                Total de problemas
              </p>
              <p className="text-2xl font-bold text-foreground">
                {result.totalIssues}
              </p>
            </div>
            <div
              className={`border rounded-lg p-3 text-center shadow-sm ${
                result.pagesWithFailures > 0
                  ? "bg-red-50 border-red-200"
                  : "bg-white"
              }`}
            >
              <p className="text-xs text-muted-foreground mb-1">Com falhas</p>
              <p
                className={`text-2xl font-bold ${
                  result.pagesWithFailures > 0
                    ? "text-red-600"
                    : "text-foreground"
                }`}
              >
                {result.pagesWithFailures}
              </p>
            </div>
            <div
              className={`border rounded-lg p-3 text-center shadow-sm ${
                (result.pagesWithWarnings || 0) > 0
                  ? "bg-amber-50 border-amber-200"
                  : "bg-white"
              }`}
            >
              <p className="text-xs text-muted-foreground mb-1">Com avisos</p>
              <p
                className={`text-2xl font-bold ${
                  (result.pagesWithWarnings || 0) > 0
                    ? "text-amber-600"
                    : "text-foreground"
                }`}
              >
                {result.pagesWithWarnings || 0}
              </p>
            </div>
            {(() => {
              const compliantPages =
                result.totalPages -
                result.pagesWithFailures -
                (result.pagesWithWarnings || 0);
              return (
                <div
                  className={`border rounded-lg p-3 text-center shadow-sm ${
                    compliantPages > 0
                      ? "bg-emerald-50 border-emerald-200"
                      : "bg-white"
                  }`}
                >
                  <p className="text-xs text-muted-foreground mb-1">
                    Sem problemas
                  </p>
                  <p
                    className={`text-2xl font-bold ${
                      compliantPages > 0
                        ? "text-emerald-600"
                        : "text-foreground"
                    }`}
                  >
                    {compliantPages}
                  </p>
                </div>
              );
            })()}
          </div>

          {result.daCache && (
            <p className="text-xs text-muted-foreground text-center italic">
              Resultado obtido da cache
            </p>
          )}

          {/* Filters */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-muted-foreground">Filtrar:</span>
            {(["all", "fail", "warn", "ok"] as const).map((f) => (
              <Button
                key={f}
                size="sm"
                variant={filter === f ? "default" : "outline"}
                className="h-7 text-xs"
                onClick={() => setFilter(f)}
              >
                {f === "all"
                  ? "Todas"
                  : f === "fail"
                    ? "Com falhas"
                    : f === "warn"
                      ? "Com avisos"
                      : "Sem problemas"}
              </Button>
            ))}
            <span className="text-xs text-muted-foreground ml-auto">
              {filteredPages.length} resultado
              {filteredPages.length !== 1 ? "s" : ""}
            </span>
          </div>

          {/* Pages list */}
          <Card className="shadow-sm overflow-hidden">
            <div className="divide-y">
              {filteredPages.length === 0 ? (
                <div className="p-8 text-center text-muted-foreground text-sm">
                  Nenhuma página corresponde ao filtro selecionado.
                </div>
              ) : (
                filteredPages.map((page, i) => (
                  <SitemapPageRow key={page.url} page={page} index={i} />
                ))
              )}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

// ─── Crawler Audit ───────────────────────────────────────────────────────────

function CrawlerAudit() {
  const [url, setUrl] = useState("");
  const [maxPages, setMaxPages] = useState<number>(100);
  const [limitPages, setLimitPages] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CrawlerAuditResult | null>(null);
  const [filter, setFilter] = useState<"all" | "fail" | "warn" | "ok">("all");

  async function handleCrawler(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setResult(null);
    const toastId = toast.loading("A rastrear e auditar páginas...", {
      description: url,
    });

    try {
      const res = await api.crawler(url.trim(), limitPages ? maxPages : 10000);
      setResult(res);
      if (res.status === "error") {
        toast.error("Erro no crawler", {
          id: toastId,
          description: res.message,
        });
      } else {
        toast.success(`Rastreio concluído - ${res.totalPages} página(s)`, {
          id: toastId,
          description: `${res.pagesWithFailures} com falhas`,
        });
      }
    } catch (err: any) {
      toast.error("Falha ao rastrear site", {
        id: toastId,
        description: err.message,
      });
    } finally {
      setLoading(false);
    }
  }

  const filteredPages =
    result?.pages.filter((p) => {
      const failCount =
        p.issues?.filter((i) => i.severity === "FAIL").length ?? 0;
      const reviewCount =
        p.issues?.filter((i) => i.severity === "REVIEW").length ?? 0;
      if (filter === "fail") return p.status === "ERROR" || failCount > 0;
      if (filter === "warn")
        return p.status !== "ERROR" && failCount === 0 && reviewCount > 0;
      if (filter === "ok")
        return p.status !== "ERROR" && failCount === 0 && reviewCount === 0;
      return true;
    }) ?? [];

  return (
    <div className="space-y-6">
      {/* Input */}
      <Card className="shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Search className="size-4 text-primary" />
            Auditar por Crawler
          </CardTitle>
          <CardDescription>
            Insira o URL semente (ex:{" "}
            <code className="bg-muted px-1 rounded text-xs">
              https://exemplo.com
            </code>
            ) - o sistema irá descobrir todos os links internos recursivamente e
            auditar os cabeçalhos de cada página encontrada.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleCrawler}
            className="flex flex-col sm:flex-row gap-3 items-end"
          >
            <div className="flex-1 space-y-1 w-full">
              <label
                htmlFor="crawler-url-input"
                className="text-xs font-medium text-muted-foreground block"
              >
                URL Semente
              </label>
              <Input
                id="crawler-url-input"
                type="url"
                placeholder="https://exemplo.com"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                disabled={loading}
                required
              />
            </div>
            <div className="flex items-center gap-2 h-10 px-1 shrink-0">
              <Checkbox
                id="crawler-limit-checkbox"
                checked={limitPages}
                onCheckedChange={(checked) => setLimitPages(!!checked)}
                disabled={loading}
              />
              <label
                htmlFor="crawler-limit-checkbox"
                className="text-xs font-medium text-muted-foreground cursor-pointer select-none"
              >
                Limitar páginas
              </label>
            </div>
            {limitPages && (
              <div className="w-full sm:w-32 space-y-1 animate-in fade-in slide-in-from-left-2 duration-200">
                <label
                  htmlFor="crawler-max-pages"
                  className="text-xs font-medium text-muted-foreground block"
                >
                  Máx. Páginas
                </label>
                <Input
                  id="crawler-max-pages"
                  type="number"
                  min={1}
                  max={500}
                  value={maxPages}
                  onChange={(e) => setMaxPages(parseInt(e.target.value) || 100)}
                  disabled={loading}
                  required
                />
              </div>
            )}
            <Button
              type="submit"
              disabled={loading}
              className="w-full sm:w-auto shrink-0"
            >
              {loading ? (
                <Loader2 className="size-4 animate-spin mr-2" />
              ) : (
                <Search className="size-4 mr-2" />
              )}
              Rastrear Site
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Loading */}
      {loading && (
        <div className="flex flex-col items-center justify-center p-16 border rounded-xl bg-muted/30 text-muted-foreground">
          <Loader2 className="size-8 animate-spin mb-4 text-primary" />
          <p className="font-medium">A rastrear e auditar páginas...</p>
          <p className="text-xs mt-1 opacity-70">
            Isto pode demorar alguns minutos dependendo do número de páginas.
          </p>
        </div>
      )}

      {/* Empty */}
      {!loading && !result && (
        <Card className="border-dashed py-16 flex flex-col items-center justify-center text-center">
          <Search className="size-12 text-muted-foreground mb-4 opacity-40" />
          <CardTitle className="text-base font-semibold">
            Auditoria Recursiva por Crawler
          </CardTitle>
          <CardDescription className="max-w-sm mt-2 text-sm">
            Insira um URL acima para rastrear o site e auditar automaticamente
            todos os seus cabeçalhos.
          </CardDescription>
        </Card>
      )}

      {/* Error status */}
      {!loading && result?.status === "error" && (
        <div className="flex items-center gap-3 p-4 border border-red-200 bg-red-50 rounded-lg text-red-700">
          <AlertCircle className="size-5 shrink-0" />
          <div className="space-y-1">
            <p className="font-medium text-sm">Erro no crawler</p>
            <p className="text-xs">{result.message}</p>
          </div>
        </div>
      )}

      {/* Results */}
      {!loading && result && result.status === "completed" && (
        <div className="space-y-4">
          {/* Timing details */}
          {(result.iniciadoEm || result.duracaoFormatada) && (
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2 bg-slate-50 border rounded-lg text-xs text-slate-500">
              {result.iniciadoEm && (
                <div className="flex items-center gap-1.5">
                  <Clock className="size-3.5 text-slate-400" />
                  <span>
                    <strong>Início:</strong>{" "}
                    {new Date(result.iniciadoEm).toLocaleString("pt-PT")}
                  </span>
                </div>
              )}
              {result.finalizadoEm && (
                <div className="flex items-center gap-1.5">
                  <Clock className="size-3.5 text-slate-400" />
                  <span>
                    <strong>Fim:</strong>{" "}
                    {new Date(result.finalizadoEm).toLocaleString("pt-PT")}
                  </span>
                </div>
              )}
              {result.duracaoFormatada && (
                <div className="flex items-center gap-1.5">
                  <Clock className="size-3.5 text-primary" />
                  <span>
                    <strong>Tempo decorrido:</strong> {result.duracaoFormatada}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Summary */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <div className="border rounded-lg p-3 text-center bg-white shadow-sm">
              <p className="text-xs text-muted-foreground mb-1">
                Páginas auditadas
              </p>
              <p className="text-2xl font-bold text-foreground">
                {result.totalPages}
              </p>
            </div>
            <div className="border rounded-lg p-3 text-center bg-white shadow-sm">
              <p className="text-xs text-muted-foreground mb-1">
                Total de problemas
              </p>
              <p className="text-2xl font-bold text-foreground">
                {result.totalIssues}
              </p>
            </div>
            <div
              className={`border rounded-lg p-3 text-center shadow-sm ${
                result.pagesWithFailures > 0
                  ? "bg-red-50 border-red-200"
                  : "bg-white"
              }`}
            >
              <p className="text-xs text-muted-foreground mb-1">Com falhas</p>
              <p
                className={`text-2xl font-bold ${
                  result.pagesWithFailures > 0
                    ? "text-red-600"
                    : "text-foreground"
                }`}
              >
                {result.pagesWithFailures}
              </p>
            </div>
            <div
              className={`border rounded-lg p-3 text-center shadow-sm ${
                (result.pagesWithWarnings || 0) > 0
                  ? "bg-amber-50 border-amber-200"
                  : "bg-white"
              }`}
            >
              <p className="text-xs text-muted-foreground mb-1">Com avisos</p>
              <p
                className={`text-2xl font-bold ${
                  (result.pagesWithWarnings || 0) > 0
                    ? "text-amber-600"
                    : "text-foreground"
                }`}
              >
                {result.pagesWithWarnings || 0}
              </p>
            </div>
            {(() => {
              const compliantPages =
                result.totalPages -
                result.pagesWithFailures -
                (result.pagesWithWarnings || 0);
              return (
                <div
                  className={`border rounded-lg p-3 text-center shadow-sm ${
                    compliantPages > 0
                      ? "bg-emerald-50 border-emerald-200"
                      : "bg-white"
                  }`}
                >
                  <p className="text-xs text-muted-foreground mb-1">
                    Sem problemas
                  </p>
                  <p
                    className={`text-2xl font-bold ${
                      compliantPages > 0
                        ? "text-emerald-600"
                        : "text-foreground"
                    }`}
                  >
                    {compliantPages}
                  </p>
                </div>
              );
            })()}
          </div>

          {result.daCache && (
            <p className="text-xs text-muted-foreground text-center italic">
              Resultado obtido da cache
            </p>
          )}

          {/* Filters */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-muted-foreground">Filtrar:</span>
            {(["all", "fail", "warn", "ok"] as const).map((f) => (
              <Button
                key={f}
                size="sm"
                variant={filter === f ? "default" : "outline"}
                className="h-7 text-xs"
                onClick={() => setFilter(f)}
              >
                {f === "all"
                  ? "Todas"
                  : f === "fail"
                    ? "Com falhas"
                    : f === "warn"
                      ? "Com avisos"
                      : "Sem problemas"}
              </Button>
            ))}
            <span className="text-xs text-muted-foreground ml-auto">
              {filteredPages.length} resultado
              {filteredPages.length !== 1 ? "s" : ""}
            </span>
          </div>

          {/* Pages list */}
          <Card className="shadow-sm overflow-hidden">
            <div className="divide-y">
              {filteredPages.length === 0 ? (
                <div className="p-8 text-center text-muted-foreground text-sm">
                  Nenhuma página corresponde ao filtro selecionado.
                </div>
              ) : (
                filteredPages.map((page, i) => (
                  <SitemapPageRow key={page.url} page={page} index={i} />
                ))
              )}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

function MultiUrlPaginationAudit() {
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<MultiUrlAuditResult | null>(null);

  async function handleMultiAudit(e: React.FormEvent) {
    e.preventDefault();

    const urls = value
      .split(/[\s,;\n\r\t]+/)
      .map((entry) => entry.trim())
      .filter(Boolean);

    if (urls.length === 0) return;

    setLoading(true);
    setResult(null);

    const toastId = toast.loading("A processar URLs e paginação...", {
      description: `${urls.length} URL(s)`,
    });

    try {
      const res = await api.multiUrlAudit(urls);
      setResult(res);
      toast.success(`Auditoria concluída - ${res.totalPages} página(s)`, {
        id: toastId,
        description: `${res.totalInputUrls} URL(s) de origem`,
      });
    } catch (err: any) {
      toast.error("Falha no audit multi-url", {
        id: toastId,
        description: err.message,
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Globe className="size-4 text-primary" />
            Multi-URL com Paginação
          </CardTitle>
          <CardDescription>
            Insira um ou mais URLs. Para cada URL, o sistema audita a página
            inicial e, se existir paginação, audita também cada página dessa
            sequência.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleMultiAudit} className="space-y-3">
            <Textarea
              value={value}
              onChange={(e) => setValue(e.target.value)}
              disabled={loading}
              placeholder={
                "https://exemplo.com/lista-1\nhttps://exemplo.com/lista-2"
              }
              className="min-h-32"
            />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-muted-foreground">
                Pode separar URLs por linha, espaço, vírgula ou ponto e vírgula.
              </p>
              <Button type="submit" disabled={loading}>
                {loading ? (
                  <Loader2 className="size-4 animate-spin mr-2" />
                ) : (
                  <Globe className="size-4 mr-2" />
                )}
                Auditar URLs
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {loading && (
        <div className="flex flex-col items-center justify-center p-16 border rounded-xl bg-muted/30 text-muted-foreground">
          <Loader2 className="size-8 animate-spin mb-4 text-primary" />
          <p className="font-medium">
            A detetar paginação e auditar páginas...
          </p>
          <p className="text-xs mt-1 opacity-70">
            Cada URL é expandido para incluir as páginas paginadas quando
            existirem.
          </p>
        </div>
      )}

      {!loading && !result && (
        <Card className="border-dashed py-16 flex flex-col items-center justify-center text-center">
          <Globe className="size-12 text-muted-foreground mb-4 opacity-40" />
          <CardTitle className="text-base font-semibold">
            Auditoria multi-URL
          </CardTitle>
          <CardDescription className="max-w-md mt-2 text-sm">
            Forneça várias páginas de entrada e o sistema tratará
            automaticamente a paginação de cada uma antes de auditar os
            cabeçalhos.
          </CardDescription>
        </Card>
      )}

      {!loading && result && (
        <div className="space-y-4">
          {/* Timing details */}
          {(result.iniciadoEm || result.duracaoFormatada) && (
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2 bg-slate-50 border rounded-lg text-xs text-slate-500">
              {result.iniciadoEm && (
                <div className="flex items-center gap-1.5">
                  <Clock className="size-3.5 text-slate-400" />
                  <span>
                    <strong>Início:</strong>{" "}
                    {new Date(result.iniciadoEm).toLocaleString("pt-PT")}
                  </span>
                </div>
              )}
              {result.finalizadoEm && (
                <div className="flex items-center gap-1.5">
                  <Clock className="size-3.5 text-slate-400" />
                  <span>
                    <strong>Fim:</strong>{" "}
                    {new Date(result.finalizadoEm).toLocaleString("pt-PT")}
                  </span>
                </div>
              )}
              {result.duracaoFormatada && (
                <div className="flex items-center gap-1.5">
                  <Clock className="size-3.5 text-primary" />
                  <span>
                    <strong>Tempo decorrido:</strong> {result.duracaoFormatada}
                  </span>
                </div>
              )}
            </div>
          )}

          <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
            <div className="border rounded-lg p-3 text-center bg-white shadow-sm">
              <p className="text-xs text-muted-foreground mb-1">
                URLs de origem
              </p>
              <p className="text-2xl font-bold text-foreground">
                {result.totalInputUrls}
              </p>
            </div>
            <div className="border rounded-lg p-3 text-center bg-white shadow-sm">
              <p className="text-xs text-muted-foreground mb-1">
                Páginas auditadas
              </p>
              <p className="text-2xl font-bold text-foreground">
                {result.totalPages}
              </p>
            </div>
            <div className="border rounded-lg p-3 text-center bg-white shadow-sm">
              <p className="text-xs text-muted-foreground mb-1">
                Total de problemas
              </p>
              <p className="text-2xl font-bold text-foreground">
                {result.totalIssues}
              </p>
            </div>
            <div
              className={`border rounded-lg p-3 text-center shadow-sm ${
                result.pagesWithFailures > 0
                  ? "bg-red-50 border-red-200"
                  : "bg-white"
              }`}
            >
              <p className="text-xs text-muted-foreground mb-1">Com falhas</p>
              <p
                className={`text-2xl font-bold ${
                  result.pagesWithFailures > 0
                    ? "text-red-600"
                    : "text-foreground"
                }`}
              >
                {result.pagesWithFailures}
              </p>
            </div>
            <div
              className={`border rounded-lg p-3 text-center shadow-sm ${
                (result.pagesWithWarnings || 0) > 0
                  ? "bg-amber-50 border-amber-200"
                  : "bg-white"
              }`}
            >
              <p className="text-xs text-muted-foreground mb-1">Com avisos</p>
              <p
                className={`text-2xl font-bold ${
                  (result.pagesWithWarnings || 0) > 0
                    ? "text-amber-600"
                    : "text-foreground"
                }`}
              >
                {result.pagesWithWarnings || 0}
              </p>
            </div>
            {(() => {
              const compliantPages =
                result.totalPages -
                result.pagesWithFailures -
                (result.pagesWithWarnings || 0);
              return (
                <div
                  className={`border rounded-lg p-3 text-center shadow-sm ${
                    compliantPages > 0
                      ? "bg-emerald-50 border-emerald-200"
                      : "bg-white"
                  }`}
                >
                  <p className="text-xs text-muted-foreground mb-1">
                    Sem problemas
                  </p>
                  <p
                    className={`text-2xl font-bold ${
                      compliantPages > 0
                        ? "text-emerald-600"
                        : "text-foreground"
                    }`}
                  >
                    {compliantPages}
                  </p>
                </div>
              );
            })()}
          </div>

          {result.daCache && (
            <p className="text-xs text-muted-foreground text-center italic">
              Resultado obtido da cache
            </p>
          )}

          <div className="space-y-4">
            {result.groups.map((group) => (
              <Card
                key={group.inputUrl}
                className="shadow-sm overflow-hidden py-2"
              >
                <CardHeader className="border-b bg-muted/20 py-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0">
                      <CardTitle className="text-sm font-semibold truncate">
                        {group.inputUrl}
                      </CardTitle>
                      <CardDescription className="mt-1 text-xs">
                        {group.hasPagination
                          ? "Paginação detetada e expandida."
                          : "Sem paginação detetada; apenas a página base foi auditada."}
                      </CardDescription>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="text-xs">
                        {group.pageCount} página
                        {group.pageCount !== 1 ? "s" : ""}
                      </Badge>
                      <Badge
                        className={
                          group.pagesWithFailures > 0
                            ? "bg-red-600 text-white hover:bg-red-700 text-xs"
                            : (group.pagesWithWarnings || 0) > 0
                              ? "bg-amber-500 text-white hover:bg-amber-600 text-xs"
                              : "bg-emerald-500 text-white hover:bg-emerald-600 text-xs"
                        }
                      >
                        {group.pagesWithFailures > 0
                          ? `${group.pagesWithFailures} com falha${group.pagesWithFailures !== 1 ? "s" : ""}`
                          : (group.pagesWithWarnings || 0) > 0
                            ? `${group.pagesWithWarnings} com aviso${group.pagesWithWarnings !== 1 ? "s" : ""}`
                            : "Sem problemas"}
                      </Badge>
                    </div>
                  </div>
                </CardHeader>
                <div className="divide-y">
                  {group.pages.map((page, index) => (
                    <SitemapPageRow
                      key={`${group.inputUrl}-${page.url}`}
                      page={page}
                      index={index}
                    />
                  ))}
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ModeDock({ pathname }: { pathname: string }) {
  const items = [
    { href: "/", label: "Página", icon: FileText, active: pathname === "/" },
    {
      href: "/multi",
      label: "Multi",
      icon: Globe,
      active: pathname === "/multi",
    },
    {
      href: "/sitemap",
      label: "Sitemap",
      icon: Map,
      active: pathname === "/sitemap",
    },
  ];

  return (
    <div className="flex flex-col items-center gap-3">
      <Dock
        iconSize={52}
        iconMagnification={66}
        className="mt-0 rounded-[1.4rem] border-slate-200/80 bg-white/80 p-2 shadow-lg shadow-slate-900/10 backdrop-blur-xl"
      >
        {items.map((item) => {
          const Icon = item.icon;

          return (
            <DockIcon
              key={item.href}
              disableMagnification={item.active}
              className={cn(
                "border transition-colors",
                item.active
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-200 bg-white text-slate-700",
              )}
            >
              <Link
                href={item.href}
                className="flex size-full items-center justify-center rounded-full"
                aria-label={item.label}
                title={item.label}
              >
                <Icon className="size-4" />
              </Link>
            </DockIcon>
          );
        })}
      </Dock>
      <div className="flex flex-wrap items-center justify-center gap-3 text-xs font-medium text-slate-500">
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "rounded-full px-2 py-1 transition-colors",
              item.active ? "bg-slate-900 text-white" : "hover:bg-white/70",
            )}
          >
            {item.label}
          </Link>
        ))}
      </div>
    </div>
  );
}

export default function PainelTeS() {
  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
      {/* Header Banner */}
      <div className="rounded-[1.75rem] border border-slate-200/80 bg-[radial-gradient(circle_at_top_left,rgba(56,189,248,0.18),transparent_24%),radial-gradient(circle_at_top_right,rgba(250,204,21,0.16),transparent_26%),linear-gradient(135deg,#fffdf7_0%,#f8fbff_52%,#eef6ff_100%)] p-6 shadow-[0_24px_90px_rgba(15,23,42,0.08)]">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-4">
            <div className="space-y-3">
              <h1 className="text-2xl font-semibold tracking-tight text-slate-950 md:text-4xl">
                <DiaTextReveal
                  className="text-2xl font-semibold tracking-tight text-slate-950 md:text-4xl"
                  text={["Verificação de Títulos e Subtítulos"]}
                  colors={["#0f766e"]}
                  fixedWidth
                />
              </h1>
              <p className="max-w-2xl text-sm leading-6 text-slate-600 md:text-base">
                Verificação automática da estrutura hierárquica de cabeçalhos.
              </p>
            </div>
          </div>
          <div className="w-full lg:w-auto"></div>
        </div>
      </div>

      {/* Mode Tabs */}
      <Tabs defaultValue="single" className="w-full">
        <TabsList className="grid w-full max-w-3xl grid-cols-4">
          <TabsTrigger value="single" id="tab-single-page">
            <FileText className="size-3.5 mr-1.5" />
            Página Única
          </TabsTrigger>
          <TabsTrigger value="multi" id="tab-multi-url">
            <Globe className="size-3.5 mr-1.5" />
            Multi-URL
          </TabsTrigger>
          <TabsTrigger value="sitemap" id="tab-sitemap">
            <Map className="size-3.5 mr-1.5" />
            Sitemap
          </TabsTrigger>
          <TabsTrigger value="crawler" id="tab-crawler">
            <Search className="size-3.5 mr-1.5" />
            Crawler
          </TabsTrigger>
        </TabsList>

        <TabsContent value="single" className="mt-6">
          <SinglePageAudit />
        </TabsContent>

        <TabsContent value="multi" className="mt-6">
          <MultiUrlPaginationAudit />
        </TabsContent>

        <TabsContent value="sitemap" className="mt-6">
          <SitemapAudit />
        </TabsContent>

        <TabsContent value="crawler" className="mt-6">
          <CrawlerAudit />
        </TabsContent>
      </Tabs>
    </div>
  );
}
