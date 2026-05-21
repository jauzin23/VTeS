"use client";

import type { ReactNode } from "react";
import { ExternalLink } from "lucide-react";
import { Safari } from "@/components/ui/safari";
import { cn } from "@/lib/utils";

interface PreviewBrowserFrameProps {
  children: ReactNode;
  url?: string;
  className?: string;
}

export function PreviewBrowserFrame({
  children,
  url,
  className,
}: PreviewBrowserFrameProps) {
  return (
    <div className={cn("relative w-full", className)}>
      <Safari
        url={url || "Preview"}
        mode="simple"
        className="pointer-events-none drop-shadow-[0_30px_80px_rgba(15,23,42,0.18)]"
      />
      <div className="absolute left-[0.2%] top-[6.9%] h-[92.95%] w-[99.75%] overflow-hidden rounded-b-[12px] bg-white">
        {children}
      </div>
      {url && (
        <div className="absolute right-4 top-3 z-20 hidden items-center gap-2 rounded-full border border-black/10 bg-white/80 px-3 py-1 text-[11px] font-medium text-slate-600 shadow-sm backdrop-blur md:flex">
          <span className="max-w-56 truncate">{url}</span>
          <ExternalLink className="size-3" />
        </div>
      )}
    </div>
  );
}
