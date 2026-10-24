"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import React from "react";

export function NavActive({
  href,
  label,
  icon,
  exact = false
}: {
  href: string;
  label: string;
  icon?: React.ReactNode;
  exact?: boolean;
}) {
  const pathname = usePathname();
  const isActive = exact ? pathname === href : pathname.startsWith(href) && (href === "/" ? pathname === "/" : true);

  return (
    <Link
      href={href}
      className={`nav-link${isActive ? " active" : ""}`}
      aria-current={isActive ? "page" : undefined}
      style={{ textDecoration: "none" }}
    >
      {icon && <span aria-hidden="true" className="nav-icon" style={{ display: "inline-flex", alignItems: "center" }}>{icon}</span>}
      <span>{label}</span>
    </Link>
  );
}

