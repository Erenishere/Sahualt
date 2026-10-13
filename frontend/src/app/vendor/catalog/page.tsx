"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { VendorHeader } from "@/components/vendor-header";
import { backendGet, backendPost, BackendRequestError } from "@/services/backend-client";
import styles from "./vendor-catalog.module.css";

type Vendor = { vendorId: string; displayName: string; role: string };
type Session = { userId: string; vendors: Vendor[] };
type Product = {
  productId: string;
  productName: string;
  productStatus: string;
  hasCategory: boolean;
  hasActiveImage: boolean;
  hasActiveDefaultVariant: boolean;
  hasCompleteListing: boolean;
};
type CatalogPage = { items: Product[]; nextAfter: string | null };
type CreatedDraft = { productId: string; productName: string; productStatus: string };

function missingRequirements(product: Product): string[] {
  const missing: string[] = [];
  if (!product.hasCategory) missing.push("active category");
  if (!product.hasActiveImage) missing.push("active image");
  if (!product.hasActiveDefaultVariant) missing.push("active default variant");
  if (!product.hasCompleteListing) missing.push("listing with price, currency, and availability");
  return missing;
}

function errorMessage(error: unknown): string {
  if (error instanceof BackendRequestError) return error.message;
  return "Catalog is unavailable. Please try again.";
}

export default function VendorCatalogPage() {
  const router = useRouter();
  const [checkingSession, setCheckingSession] = useState(true);
  const [session, setSession] = useState<Session | null>(null);
  const [vendorId, setVendorId] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [nextAfter, setNextAfter] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const requestEpoch = useRef(0);

  useEffect(() => {
    let active = true;
    backendGet<Session>("/api/v1/auth/me")
      .then((current) => {
        if (!active) return;
        setSession(current);
        setVendorId(current.vendors[0]?.vendorId ?? "");
      })
      .catch((reason: unknown) => {
        if (active && !(reason instanceof BackendRequestError && reason.status === 401))
          setError(errorMessage(reason));
      })
      .finally(() => { if (active) setCheckingSession(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const epoch = ++requestEpoch.current;
    setProducts([]);
    setNextAfter(null);
    setLoadingMore(false);
    setError("");
    if (!vendorId) return;
    setLoading(true);
    backendGet<CatalogPage>(`/api/v1/vendors/${encodeURIComponent(vendorId)}/catalog/products`)
      .then((page) => {
        if (requestEpoch.current !== epoch) return;
        setProducts(page.items);
        setNextAfter(page.nextAfter);
      })
      .catch((reason: unknown) => {
        if (requestEpoch.current !== epoch) return;
        if (reason instanceof BackendRequestError && reason.status === 401) {
          setSession(null);
          setVendorId("");
        }
        setError(errorMessage(reason));
      })
      .finally(() => { if (requestEpoch.current === epoch) setLoading(false); });
  }, [vendorId]);

  async function loadMore() {
    if (!vendorId || !nextAfter || loadingMore) return;
    const epoch = requestEpoch.current;
    setLoadingMore(true);
    setError("");
    try {
      const page = await backendGet<CatalogPage>(
        `/api/v1/vendors/${encodeURIComponent(vendorId)}/catalog/products?after=${encodeURIComponent(nextAfter)}`,
      );
      if (requestEpoch.current !== epoch) return;
      setProducts((current) => [...current, ...page.items]);
      setNextAfter(page.nextAfter);
    } catch (reason) {
      if (requestEpoch.current !== epoch) return;
      if (reason instanceof BackendRequestError && reason.status === 401) {
        setSession(null);
        setVendorId("");
      }
      setError(errorMessage(reason));
    } finally {
      if (requestEpoch.current === epoch) setLoadingMore(false);
    }
  }

  async function createDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedName = name.trim();
    const trimmedDescription = description.trim();
    if (!vendorId || !trimmedName || !trimmedDescription || creating) return;
    const targetVendorId = vendorId;
    setCreating(true);
    setError("");
    try {
      const product = await backendPost<CreatedDraft>(
        `/api/v1/vendors/${encodeURIComponent(targetVendorId)}/catalog/products`,
        { name: trimmedName, description: trimmedDescription },
      );
      router.push(`/vendor/${encodeURIComponent(targetVendorId)}/products/${encodeURIComponent(product.productId)}`);
    } catch (reason) {
      if (reason instanceof BackendRequestError && reason.status === 401) {
        setSession(null);
        setVendorId("");
      }
      setError(errorMessage(reason));
    } finally {
      setCreating(false);
    }
  }

  const canEdit = session?.vendors.find((vendor) => vendor.vendorId === vendorId)?.role;
  const showCreateForm = canEdit === "owner" || canEdit === "manager" || canEdit === "staff";

  return <main className={styles.page}>
    <VendorHeader />
    <section className={styles.panel} aria-labelledby="catalog-title">
      <p className={styles.eyebrow}>Vendor workspace</p>
      <h1 id="catalog-title">Your catalog</h1>
      <p className={styles.intro}>Review products and the records needed for publication. This view does not change listings.</p>

      {checkingSession ? <p role="status">Checking your session…</p> : !session ? (
        <div className={styles.card}>
          <h2>Sign in to view your catalog</h2>
          <p>Your products are available only to active members of your vendor account.</p>
          <Link className={styles.link} href="/vendor/assistant">Go to vendor sign in</Link>
        </div>
      ) : session.vendors.length === 0 ? (
        <div className={styles.card}>Your account has no active vendor membership.</div>
      ) : <>
        <label className={styles.vendorSelect}>Vendor
          <select value={vendorId} disabled={creating} onChange={(event) => setVendorId(event.target.value)}>
            {session.vendors.map((vendor) => <option key={vendor.vendorId} value={vendor.vendorId}>{vendor.displayName}</option>)}
          </select>
        </label>
        {showCreateForm && <form className={styles.createForm} onSubmit={createDraft}>
          <h2>Add a draft product</h2>
          <p>Start a product record for this vendor. It remains a draft; images, variants, listings, and publication are separate steps.</p>
          <label>Product name
            <input value={name} onChange={(event) => setName(event.target.value)} maxLength={200} required />
          </label>
          <label>Description
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={5000} rows={3} required />
          </label>
          <button type="submit" disabled={creating || !name.trim() || !description.trim()}>
            {creating ? "Creating…" : "Create draft"}
          </button>
        </form>}
        {loading ? <p role="status">Loading products…</p> : products.length === 0 && !error ? (
          <div className={styles.card}>
            <h2>No products yet</h2>
            <p>Draft products created by your team will appear here. No sample products are shown as live inventory.</p>
          </div>
        ) : <div className={styles.grid}>
          {products.map((product) => {
            const missing = missingRequirements(product);
            return <article className={styles.card} key={product.productId}>
              <div className={styles.cardTop}>
                <h2>{product.productName}</h2>
                <span className={styles.status}>{product.productStatus}</span>
              </div>
              {missing.length === 0 ? (
                <p className={styles.ready}>Catalog prerequisites present</p>
              ) : <p className={styles.missing}>Needs: {missing.join(", ")}</p>}
              <Link className={styles.link} href={`/vendor/${encodeURIComponent(vendorId)}/products/${encodeURIComponent(product.productId)}`}>View product and listings</Link>
            </article>;
          })}
        </div>}
        {nextAfter && <button className={styles.loadMore} type="button" disabled={loadingMore} onClick={loadMore}>
          {loadingMore ? "Loading…" : "Load more products"}
        </button>}
      </>}
      {error && <p className={styles.error} role="alert">{error}</p>}
    </section>
  </main>;
}
