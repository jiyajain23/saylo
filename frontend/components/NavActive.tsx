"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function NavActive({
  href,
  label,
  icon,
  exact = false
}: {
  href: string;
  label: string;
  icon: string;
  exact?: boolean;
}) {
  const pathname = usePathname();
  const isActive = exact ? pathname === href : pathname.startsWith(href) && (href === "/" ? pathname === "/" : true);

  return (
    <Link
      href={href}
      className={`nav-link${isActive ? " active" : ""}`}
      style={{ textDecoration: "none" }}
    >
      <span style={{ fontSize: "1rem", lineHeight: 1 }}>{icon}</span>
      <span>{label}</span>
    </Link>
  );
}
