import type { Metadata } from "next";
import Link from "next/link";
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
        <nav className="globalNav" aria-label="Genesis sections">
          <Link href="/">Workstation</Link>
          <Link href="/research">Research</Link>
          <Link href="/connections">Connections</Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
