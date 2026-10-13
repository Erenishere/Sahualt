"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { VendorHeader } from "@/components/vendor-header";
import { backendPost, BackendRequestError } from "@/services/backend-client";
import styles from "./vendor-register.module.css";

export default function VendorRegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [contactName, setContactName] = useState("");
  const [vendorName, setVendorName] = useState("");
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await backendPost("/api/v1/auth/vendor-registrations", { email, password, contactName, vendorName });
      setPassword("");
      setPending(true);
    } catch (reason) {
      setPassword("");
      setError(reason instanceof BackendRequestError ? reason.message : "Registration is unavailable. Try again later.");
    } finally {
      setBusy(false);
    }
  }

  return <main className={styles.page}>
    <VendorHeader />
    <section className={styles.panel}>
      <p className={styles.eyebrow}>Vendor workspace</p>
      <h1>Register your vendor</h1>
      <p className={styles.intro}>Create a local vendor application. Catalog access starts after local review.</p>
      {pending ? <div className={styles.notice} role="status">
        <h2>Registration received</h2>
        <p>If eligible, your account is pending local review. You can sign in after approval.</p>
        <Link href="/vendor/assistant">Go to sign in</Link>
      </div> : <form className={styles.form} onSubmit={submit}>
        <label>Contact name<input autoComplete="name" required maxLength={200} value={contactName} onChange={(event) => setContactName(event.target.value)} /></label>
        <label>Vendor name<input required maxLength={200} value={vendorName} onChange={(event) => setVendorName(event.target.value)} /></label>
        <label>Email<input type="email" autoComplete="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} /></label>
        <label>Password<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        <button type="submit" disabled={busy}>{busy ? "Submitting…" : "Submit registration"}</button>
        {error && <p className={styles.error} role="alert">{error}</p>}
      </form>}
    </section>
  </main>;
}
