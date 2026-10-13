"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { VendorHeader } from "@/components/vendor-header";
import { useVendorGate } from "@/hooks/use-vendor-gate";
import { formatMoney, formatOfferStatus, formatOrderStatus } from "@/services/marketplace-api";
import {
  vendorAnalytics,
  vendorDecideOffer,
  vendorError,
  vendorOffers,
  vendorOrders,
  vendorSettings,
  vendorSummary,
  vendorTransitionOrder,
  updateVendorSettings,
} from "@/services/vendor-api";
import styles from "./vendor-workspace.module.css";

function VendorShell({ children }: { children: React.ReactNode }) {
  const gate = useVendorGate();
  if (gate.kind === "loading") {
    return <div className={styles.shell}><VendorHeader /><main className={styles.main}><p className={styles.card} role="status">Loading vendor workspace…</p></main></div>;
  }
  if (gate.kind === "no-vendor") {
    return (
      <div className={styles.shell}>
        <VendorHeader />
        <main className={styles.main}>
          <section className={styles.card}>
            <h1>No vendor store</h1>
            <p>Register a store or ask an owner to add you as a member.</p>
            <Link href="/vendor/register">Register as vendor</Link>
          </section>
        </main>
      </div>
    );
  }
  if (gate.kind !== "ready") return null;
  return <div className={styles.shell}>{children}</div>;
}

export function VendorDashboard() {
  const gate = useVendorGate();
  const vendorId = gate.kind === "ready" ? gate.vendorId : null;
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof vendorSummary>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!vendorId) return;
    let active = true;
    setLoading(true);
    setSummary(null);
    setError("");
    vendorSummary(vendorId)
      .then((result) => { if (active) setSummary(result); })
      .catch((reason) => { if (active) setError(vendorError(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [vendorId]);

  return (
    <VendorShell>
      <VendorHeader />
      <main className={styles.main}>
        <p className={styles.eyebrow}>Vendor workspace</p>
        <h1>Vendor overview</h1>
        <p className={styles.lead}>Your catalog and store activity in one place.</p>
        {loading && <p className={styles.card} role="status">Loading overview…</p>}
        {error && <p className={styles.error} role="alert">{error}</p>}
        {summary && !loading && (
          <div className={styles.metrics}>
            <article className={styles.metric}><small>Pending offers</small><b>{summary.pendingOffers}</b></article>
            <article className={styles.metric}><small>Open orders</small><b>{summary.openOrders}</b></article>
            <article className={styles.metric}><small>Low stock</small><b>{summary.lowStockListings}</b></article>
            <article className={styles.metric}><small>Unknown stock</small><b>{summary.unknownStockListings}</b></article>
          </div>
        )}
        <section className={styles.card}>
          <h2>Continue working</h2>
          <div className={styles.quickLinks}>
            <Link href="/vendor/catalog">Manage catalog <span aria-hidden="true">→</span></Link>
            <Link href="/vendor/assistant">Business assistant <span aria-hidden="true">→</span></Link>
          </div>
        </section>
      </main>
    </VendorShell>
  );
}

export function VendorOffersPage() {
  const gate = useVendorGate();
  const vendorId = gate.kind === "ready" ? gate.vendorId : null;
  const [offers, setOffers] = useState<Awaited<ReturnType<typeof vendorOffers>>>([]);
  const [loading, setLoading] = useState(true);
  const [busyOfferId, setBusyOfferId] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!vendorId) return;
    let active = true;
    setLoading(true);
    setOffers([]);
    setError("");
    vendorOffers(vendorId)
      .then((result) => { if (active) setOffers(result); })
      .catch((reason) => { if (active) setError(vendorError(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [vendorId]);

  async function decide(offer: Awaited<ReturnType<typeof vendorOffers>>[number], action: "accept" | "counter" | "reject") {
    if (!vendorId || busyOfferId) return;
    setBusyOfferId(offer.offerId);
    setError("");
    try {
      await vendorDecideOffer(vendorId, offer.offerId, action, action === "counter" ? offer.offeredPrice + 100 : undefined);
      setOffers(await vendorOffers(vendorId));
    } catch (reason) {
      setError(vendorError(reason));
    } finally {
      setBusyOfferId(null);
    }
  }

  return (
    <VendorShell>
      <VendorHeader />
      <main className={styles.main}>
        <p className={styles.eyebrow}>Vendor workspace</p>
        <h1>Customer offers</h1>
        <p className={styles.lead}>Review incoming offers and respond to pending requests.</p>
        {loading && <p className={styles.card} role="status">Loading offers…</p>}
        {error && <p className={styles.error} role="alert">{error}</p>}
        {!loading && !error && offers.length === 0 && <p className={styles.empty}>No offers yet. New customer offers will appear here.</p>}
        {!loading && offers.length > 0 && <div className={styles.list}>
          {offers.map((offer) => (
            <article className={styles.item} key={offer.offerId}>
              <div className={styles.itemTop}>
                <div><h2>{offer.productName}</h2><p>{offer.offerNumber}</p></div>
                <span className={styles.badge}>{formatOfferStatus(offer.status)}</span>
              </div>
              <p>Customer offer <strong>{formatMoney(offer.offeredPrice, offer.currency)}</strong></p>
              {offer.status === "pending" && <div className={styles.actions}>
                <button type="button" disabled={busyOfferId !== null} onClick={() => void decide(offer, "accept")}>Accept</button>
                <button type="button" className={styles.secondary} disabled={busyOfferId !== null} onClick={() => void decide(offer, "counter")}>Counter</button>
                <button type="button" className={styles.secondary} disabled={busyOfferId !== null} onClick={() => void decide(offer, "reject")}>Reject</button>
              </div>}
            </article>
          ))}
        </div>}
      </main>
    </VendorShell>
  );
}

export function VendorOrdersPage() {
  const gate = useVendorGate();
  const vendorId = gate.kind === "ready" ? gate.vendorId : null;
  const [orders, setOrders] = useState<Awaited<ReturnType<typeof vendorOrders>>>([]);
  const [loading, setLoading] = useState(true);
  const [busyOrderId, setBusyOrderId] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!vendorId) return;
    let active = true;
    setLoading(true);
    setOrders([]);
    setError("");
    vendorOrders(vendorId)
      .then((result) => { if (active) setOrders(result); })
      .catch((reason) => { if (active) setError(vendorError(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [vendorId]);

  async function confirm(orderId: string) {
    if (!vendorId || busyOrderId) return;
    setBusyOrderId(orderId);
    setError("");
    try {
      await vendorTransitionOrder(vendorId, orderId, "confirmed");
      setOrders(await vendorOrders(vendorId));
    } catch (reason) {
      setError(vendorError(reason));
    } finally {
      setBusyOrderId(null);
    }
  }

  return (
    <VendorShell>
      <VendorHeader />
      <main className={styles.main}>
        <p className={styles.eyebrow}>Vendor workspace</p>
        <h1>Orders</h1>
        <p className={styles.lead}>Track customer orders and confirm newly placed orders.</p>
        {loading && <p className={styles.card} role="status">Loading orders…</p>}
        {error && <p className={styles.error} role="alert">{error}</p>}
        {!loading && !error && orders.length === 0 && <p className={styles.empty}>No orders yet. New orders will appear here.</p>}
        {!loading && orders.length > 0 && <div className={styles.list}>
          {orders.map((order) => (
            <article className={styles.item} key={order.orderId}>
              <div className={styles.itemTop}>
                <div><h2>{order.orderNumber}</h2><p>Total: <strong>{formatMoney(order.total, order.currency)}</strong></p></div>
                <span className={styles.badge}>{formatOrderStatus(order.status)}</span>
              </div>
              {order.status === "placed" && <div className={styles.actions}>
                <button type="button" disabled={busyOrderId !== null} onClick={() => void confirm(order.orderId)}>
                  {busyOrderId === order.orderId ? "Confirming…" : "Mark confirmed"}
                </button>
              </div>}
            </article>
          ))}
        </div>}
      </main>
    </VendorShell>
  );
}

export function VendorAnalyticsPage() {
  const gate = useVendorGate();
  const vendorId = gate.kind === "ready" ? gate.vendorId : null;
  const [data, setData] = useState<Awaited<ReturnType<typeof vendorAnalytics>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!vendorId) return;
    let active = true;
    setLoading(true);
    setData(null);
    setError("");
    vendorAnalytics(vendorId, 30)
      .then((result) => { if (active) setData(result); })
      .catch((reason) => { if (active) setError(vendorError(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [vendorId]);

  return (
    <VendorShell>
      <VendorHeader />
      <main className={styles.main}>
        <p className={styles.eyebrow}>Vendor workspace</p>
        <h1>Analytics</h1>
        <p className={styles.lead}>Recorded order and offer activity over the last 30 days.</p>
        {loading && <p className={styles.card} role="status">Loading analytics…</p>}
        {error && <p className={styles.error} role="alert">{error}</p>}
        {data && !loading && <div className={styles.metrics}>
          <article className={styles.metric}><small>Orders placed</small><b>{data.ordersPlaced}</b></article>
          <article className={styles.metric}><small>Orders completed</small><b>{data.ordersCompleted}</b></article>
          <article className={styles.metric}><small>Offers received</small><b>{data.offersReceived}</b></article>
          <article className={styles.metric}><small>Offers accepted</small><b>{data.offersAccepted}</b></article>
        </div>}
      </main>
    </VendorShell>
  );
}

export function VendorSettingsPage() {
  const gate = useVendorGate();
  const vendorId = gate.kind === "ready" ? gate.vendorId : null;
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [allowOffers, setAllowOffers] = useState(true);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!vendorId) return;
    let active = true;
    setLoading(true);
    setLoaded(false);
    setError("");
    vendorSettings(vendorId)
      .then((settings) => {
        if (!active) return;
        setName(settings.displayName);
        setDescription(settings.description ?? "");
        setAllowOffers(settings.allowCustomerOffers);
        setLoaded(true);
      })
      .catch((reason) => { if (active) setError(vendorError(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [vendorId]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!vendorId || saving) return;
    setSaving(true);
    setNotice("");
    setError("");
    try {
      await updateVendorSettings(vendorId, { displayName: name.trim(), description: description.trim(), allowCustomerOffers: allowOffers });
      setNotice("Store settings saved.");
    } catch (reason) {
      setError(vendorError(reason));
    } finally {
      setSaving(false);
    }
  }

  return (
    <VendorShell>
      <VendorHeader />
      <main className={styles.main}>
        <p className={styles.eyebrow}>Vendor workspace</p>
        <h1>Store settings</h1>
        <p className={styles.lead}>Update the details customers see on your storefront.</p>
        {loading && <p className={styles.card} role="status">Loading settings…</p>}
        {error && <p className={styles.error} role="alert">{error}</p>}
        {!loading && loaded && <form className={styles.form} onSubmit={save}>
          <label className={styles.field}>Store name
            <input value={name} onChange={(event) => setName(event.target.value)} required />
          </label>
          <label className={styles.field}>Description
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={5} />
          </label>
          <label className={styles.checkbox}>
            <input type="checkbox" checked={allowOffers} onChange={(event) => setAllowOffers(event.target.checked)} />
            Allow customer offers
          </label>
          {notice && <p className={styles.notice} role="status">{notice}</p>}
          <button type="submit" disabled={saving || !name.trim()}>{saving ? "Saving…" : "Save settings"}</button>
        </form>}
      </main>
    </VendorShell>
  );
}
