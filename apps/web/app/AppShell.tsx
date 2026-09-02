"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const PRIMARY = [
  { href: "/", label: "Workbench" },
  { href: "/projects", label: "Projects" },
  { href: "/activity", label: "Activity" },
  { href: "/settings", label: "Settings" },
];

function activePath(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const setupSurface = pathname.startsWith("/setup");

  if (setupSurface) return <>{children}</>;

  return (
    <div className="productShell">
      <aside className="productRail" aria-label="Genesis navigation">
        <Link className="brandMark" href="/" aria-label="Genesis Workbench">
          <span className="brandGlyph">G</span>
          <span className="brandText">Genesis</span>
        </Link>

        <nav className="primaryNav">
          {PRIMARY.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={activePath(pathname, item.href) ? "active" : ""}
              aria-current={activePath(pathname, item.href) ? "page" : undefined}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="railFooter">
          <kbd>Ctrl K</kbd>
          <span>commands</span>
        </div>
      </aside>
      <div className="productSurface">{children}</div>
    </div>
  );
}
