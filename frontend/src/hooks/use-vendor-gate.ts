"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useActiveVendor } from "@/hooks/use-active-vendor";

export type VendorGateState =
  | { kind: "loading" }
  | { kind: "unauthenticated" }
  | { kind: "no-vendor" }
  | { kind: "ready"; vendorId: string };

export function useVendorGate(): VendorGateState {
  const { vendorId, loading, session } = useActiveVendor();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !session) router.replace("/login");
  }, [loading, session, router]);

  if (loading) return { kind: "loading" };
  if (!session) return { kind: "unauthenticated" };
  if (!vendorId) return { kind: "no-vendor" };
  return { kind: "ready", vendorId };
}
