"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/context/session-context";
import { SahulatBrand } from "@/components/sahulat-brand";
import styles from "./admin-workspace.module.css";
import {
  adminError,
  adminSummary,
  adminUsers,
  adminVendors,
  setUserStatus,
  setVendorStatus,
  type AdminUser,
  type AdminVendor,
} from "@/services/admin-api";

function AdminNav({ path }: { path: string }) {
  const links = [
    ["/admin", "Dashboard"],
    ["/admin/vendors", "Vendors"],
    ["/admin/users", "Users"],
  ] as const;
  return (
    <header className="topbar vendor-topbar">
      <SahulatBrand className="brand" href="/" descriptor="ADMIN" />
      <nav className="vendor-topbar-nav" aria-label="Admin navigation">
        {links.map(([href, label]) => (
          <Link key={href} href={href} className={path === href ? "on" : undefined}>{label}</Link>
        ))}
      </nav>
    </header>
  );
}

function useAdminGate() {
  const { session, loading } = useSession();
  const router = useRouter();
  const isAdmin = session?.roles?.includes("admin") ?? false;

  useEffect(() => {
    if (!loading && !session) router.replace("/login");
    if (!loading && session && !isAdmin) router.replace("/");
  }, [loading, session, isAdmin, router]);

  return { loading, session, isAdmin };
}

export function AdminDashboard({ path = "/admin" }: { path?: string }) {
  const gate = useAdminGate();
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof adminSummary>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!gate.isAdmin) return;
    let active = true;
    setLoading(true);
    adminSummary()
      .then((result) => { if (active) setSummary(result); })
      .catch((reason) => { if (active) setError(adminError(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [gate.isAdmin]);

  if (gate.loading || !gate.session) return <main className="page"><p role="status">Loading…</p></main>;
  if (!gate.isAdmin) return null;

  return (
    <>
      <AdminNav path={path} />
      <main className={styles.main}>
        <p className={styles.eyebrow}>Platform administration</p>
        <h1>Platform overview</h1>
        <p className={styles.lead}>Review vendor approvals and platform accounts.</p>
        {loading && <p className={styles.loading} role="status">Loading platform overview…</p>}
        {error && <p className={styles.error} role="alert">{error}</p>}
        {summary && !loading && (
          <div className={styles.metrics}>
            <article className={styles.metric}><small>Vendors</small><b>{summary.registeredVendors}</b></article>
            <article className={styles.metric}><small>Active listings</small><b>{summary.activeListings}</b></article>
            <article className={styles.metric}><small>Users</small><b>{summary.registeredUsers}</b></article>
            <article className={styles.metric}><small>Pending vendors</small><b>{summary.pendingVendors}</b></article>
          </div>
        )}
      </main>
    </>
  );
}

export function AdminUsersPage() {
  const gate = useAdminGate();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyUserId, setBusyUserId] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!gate.isAdmin) return;
    let active = true;
    setLoading(true);
    adminUsers()
      .then((result) => { if (active) setUsers(result); })
      .catch((reason) => { if (active) setError(adminError(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [gate.isAdmin]);

  async function changeStatus(user: AdminUser) {
    if (busyUserId) return;
    setBusyUserId(user.userId);
    setError("");
    try {
      await setUserStatus(user.userId, user.status === "active" ? "suspended" : "active");
      setUsers(await adminUsers());
    } catch (reason) {
      setError(adminError(reason));
    } finally {
      setBusyUserId(null);
    }
  }

  if (gate.loading || !gate.session) return <main className="page"><p role="status">Loading…</p></main>;
  if (!gate.isAdmin) return null;

  return (
    <>
      <AdminNav path="/admin/users" />
      <main className={styles.main}>
        <p className={styles.eyebrow}>Platform administration</p>
        <h1>Users</h1>
        <p className={styles.lead}>Manage account access across the platform.</p>
        {loading && <p className={styles.loading} role="status">Loading users…</p>}
        {error && <p className={styles.error} role="alert">{error}</p>}
        {!loading && !error && users.length === 0 && <p className={styles.empty}>No users found.</p>}
        {!loading && users.length > 0 && <div className={styles.tableWrap}><table className={styles.table}>
          <thead><tr><th>Email</th><th>Name</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.userId}>
                <td>{u.email}</td>
                <td>{u.displayName}</td>
                <td>{u.status}</td>
                <td>
                  <button type="button" disabled={busyUserId !== null} onClick={() => void changeStatus(u)}>
                    {busyUserId === u.userId ? "Updating…" : u.status === "active" ? "Suspend" : "Activate"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>}
      </main>
    </>
  );
}

export function AdminVendorsPage() {
  const gate = useAdminGate();
  const [vendors, setVendors] = useState<AdminVendor[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyVendorId, setBusyVendorId] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!gate.isAdmin) return;
    let active = true;
    setLoading(true);
    adminVendors()
      .then((result) => { if (active) setVendors(result); })
      .catch((reason) => { if (active) setError(adminError(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [gate.isAdmin]);

  async function changeStatus(vendorId: string, status: "active" | "suspended") {
    if (busyVendorId) return;
    setBusyVendorId(vendorId);
    setError("");
    try {
      await setVendorStatus(vendorId, status);
      setVendors(await adminVendors());
    } catch (reason) {
      setError(adminError(reason));
    } finally {
      setBusyVendorId(null);
    }
  }

  if (gate.loading || !gate.session) return <main className="page"><p role="status">Loading…</p></main>;
  if (!gate.isAdmin) return null;

  return (
    <>
      <AdminNav path="/admin/vendors" />
      <main className={styles.main}>
        <p className={styles.eyebrow}>Platform administration</p>
        <h1>Vendors</h1>
        <p className={styles.lead}>Review vendor applications and storefront access.</p>
        {loading && <p className={styles.loading} role="status">Loading vendors…</p>}
        {error && <p className={styles.error} role="alert">{error}</p>}
        {!loading && !error && vendors.length === 0 && <p className={styles.empty}>No vendors found.</p>}
        {!loading && vendors.length > 0 && <div className={styles.tableWrap}><table className={styles.table}>
          <thead><tr><th>Store</th><th>Slug</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {vendors.map((v) => (
              <tr key={v.vendorId}>
                <td>{v.displayName}</td>
                <td><Link href={`/shop/${v.slug}`}>{v.slug}</Link></td>
                <td>{v.status}</td>
                <td>
                  {v.status === "pending" && (
                    <button type="button" disabled={busyVendorId !== null} onClick={() => void changeStatus(v.vendorId, "active")}>{busyVendorId === v.vendorId ? "Updating…" : "Approve"}</button>
                  )}
                  {v.status === "active" && (
                    <button type="button" disabled={busyVendorId !== null} onClick={() => void changeStatus(v.vendorId, "suspended")}>{busyVendorId === v.vendorId ? "Updating…" : "Suspend"}</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>}
      </main>
    </>
  );
}
