import type { Metadata, Viewport } from "next";
import { Toaster } from "@/components/ui/sonner";
import "./globals.css";

export const metadata: Metadata = {
  title: "Verificação de Títulos e Subtítulos",
  description:
    "Ferramenta de auditoria automática de estruturas de cabeçalhos HTML (H1-H6) por página ou sitemap.",
};

export const viewport: Viewport = {
  themeColor: "#ffffff",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-PT" className="bg-background">
      <body className="min-h-svh font-sans antialiased">
        <div className="flex min-h-svh flex-col">
          <main className="mx-auto w-full max-w-7xl flex-1 p-4 md:p-6 lg:p-8">
            {children}
          </main>
        </div>
        <Toaster richColors position="top-right" />
      </body>
    </html>
  );
}
