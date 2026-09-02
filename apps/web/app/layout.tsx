import type { Metadata } from "next";
import "@xterm/xterm/css/xterm.css";
import AppShell from "./AppShell";
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
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
