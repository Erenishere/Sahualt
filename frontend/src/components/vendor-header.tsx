"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SahulatBrand } from "@/components/sahulat-brand";

export function VendorHeader() {
  const pathname = usePathname();
  const links = [
    ["/vendor", "Overview"],
    ["/vendor/catalog", "Catalog"],
    ["/vendor/offers", "Offers"],
    ["/vendor/orders", "Orders"],
    ["/vendor/analytics", "Analytics"],
    ["/vendor/assistant", "Assistant"],
    ["/vendor/settings", "Settings"],
  ] as const;

  return (
    <header className="topbar vendor-topbar">
      <SahulatBrand className="brand" href="/" />
      <span className="vendor-topbar-label">Vendor workspace</span>
      <nav className="vendor-topbar-nav" aria-label="Vendor navigation">
        {links.map(([href, label]) => (
          <Link key={href} href={href} aria-current={pathname === href || (href === "/vendor/catalog" && pathname.startsWith("/vendor/") && pathname.includes("/products/")) ? "page" : undefined}>
            {label}
          </Link>
        ))}
        <Link href="/">Shop</Link>
      </nav>
    </header>
  );
}
