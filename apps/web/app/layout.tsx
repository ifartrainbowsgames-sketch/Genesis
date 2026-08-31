import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Genesis",
  description: "Local-first personal AI workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
