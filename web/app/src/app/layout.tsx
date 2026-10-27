import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { DISCLAIMER } from "@/lib/disclaimer";
import "./globals.css";

export const metadata: Metadata = {
  title: "CSE Screening",
  description: "Local view of the CSE screening pipeline output",
};

const NAV = [
  { href: "/", label: "Runs" },
  { href: "/review", label: "Review queue" },
  { href: "/upload", label: "Upload a filing" },
];

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-bg text-ink">
        <header className="no-print border-b border-line bg-surface">
          <nav className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
            <span className="font-semibold">CSE Screening</span>
            {NAV.map((item) => (
              <Link key={item.href} href={item.href} className="text-sm text-accent hover:underline">
                {item.label}
              </Link>
            ))}
          </nav>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 pb-10">
          <p className="rounded border border-line bg-warn-bg px-3 py-2 text-xs text-warn-ink">
            {DISCLAIMER}
          </p>
        </footer>
      </body>
    </html>
  );
}
