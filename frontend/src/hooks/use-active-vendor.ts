"use client";

import { useEffect, useState } from "react";
import { useSession } from "@/context/session-context";
import { backendGet } from "@/services/backend-client";

type SessionVendor = { vendorId: string; role: string };

export function useActiveVendor() {
  const { session, loading } = useSession();
  const [vendorId, setVendorId] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    if (loading) return;
    if (!session) {
      setVendorId(null);
      setRole(null);
      return;
    }
    backendGet<{ vendors: SessionVendor[] }>("/api/v1/auth/me")
      .then((me) => {
        const first = me.vendors[0];
        setVendorId(first?.vendorId ?? null);
        setRole(first?.role ?? null);
      })
      .catch(() => {
        setVendorId(session.vendors[0]?.vendorId ?? null);
        setRole(session.vendors[0]?.role ?? null);
      });
  }, [session, loading]);

  return { vendorId, role, session, loading };
}
