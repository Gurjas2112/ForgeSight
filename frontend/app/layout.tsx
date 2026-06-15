import type { Metadata } from "next";
import Link from "next/link";
import { Activity } from "lucide-react";
import "./globals.css";

export const metadata: Metadata = {
  title: "ForgeSight — Maintenance Wizard",
  description: "Governed multi-agent maintenance decision-support for steel plants",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <header className="flex items-center gap-3 px-5 h-14 border-b border-[#232B35] bg-[#0E1116] sticky top-0 z-20">
          <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <Activity size={18} className="text-[#FF6A2B]" />
            Forge<span className="text-[#4A90D9]">Sight</span>
          </Link>
          <span className="text-xs text-[#8B98A5] ml-1">Intelligent Maintenance Wizard · Tata Steel</span>
          <nav className="ml-auto flex items-center gap-4 text-sm text-[#8B98A5]">
            <Link href="/" className="hover:text-[#E6EDF3]">Plant Overview</Link>
            <span className="px-2 py-0.5 rounded bg-[#161B22] border border-[#232B35] text-xs">
              engineer@demo · <span className="text-[#3FB68B]">SLM-only · on-prem</span>
            </span>
          </nav>
        </header>
        <main className="flex-1">{children}</main>
      </body>
    </html>
  );
}
