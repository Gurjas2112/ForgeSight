import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/components/AuthProvider";
import { Navbar } from "@/components/Navbar";
import { CopilotWidget } from "@/components/CopilotWidget";

export const metadata: Metadata = {
  title: "ForgeSight — Maintenance Wizard",
  description: "Governed multi-agent maintenance decision-support for steel plants",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <AuthProvider>
          <Navbar />
          <main className="flex-1">{children}</main>
          <CopilotWidget />
        </AuthProvider>
      </body>
    </html>
  );
}
