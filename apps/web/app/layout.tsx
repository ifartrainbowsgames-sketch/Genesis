import type { Metadata } from "next";
import Link from "next/link";
import "@xterm/xterm/css/xterm.css";
import SetupGate from "./SetupGate";
import "./globals.css";
import "./nav.css";

export const metadata: Metadata = {
  title: "Genesis",
  description: "Local-first personal AI workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <SetupGate />
        <nav className="globalNav" aria-label="Genesis sections">
          <Link href="/">Workstation</Link>
          <Link href="/workbench">Workbench</Link>
          <Link href="/runtime">Runtime</Link>
          <Link href="/memory">Memory</Link>
          <Link href="/evolution">Evolution</Link>
          <Link href="/research">Research</Link>
          <Link href="/voice">Voice</Link>
          <Link href="/connections">Connections</Link>
          <Link href="/diagnostics">Diagnostics</Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
