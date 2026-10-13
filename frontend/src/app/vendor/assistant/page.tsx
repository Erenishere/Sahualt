"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { VendorHeader } from "@/components/vendor-header";
import { backendGet, backendPost, BackendRequestError } from "@/services/backend-client";
import styles from "./vendor-assistant.module.css";

type Vendor = { vendorId: string; displayName: string; role: string };
type Session = { userId: string; vendors: Vendor[] };
type Evidence = {
  entityType: string;
  entityId: string;
  label: string;
  observedAt: string;
  productId: string;
};
type Answer = {
  answer: string;
  intent: string;
  outcome: "answered" | "needs_clarification" | "unsupported" | "not_found" | "unavailable";
  evidence: Evidence[];
  correlationId: string;
};

const prompts = [
  "Which products are low in stock?",
  "Show my active listings",
  "Which listings are still drafts?",
  "Which products are still drafts?",
  "Which products have unknown stock?",
];

function errorMessage(error: unknown): string {
  if (error instanceof BackendRequestError) return error.message;
  return "The assistant is unavailable. Please try again.";
}

export default function VendorAssistantPage() {
  const [checkingSession, setCheckingSession] = useState(true);
  const [session, setSession] = useState<Session | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [vendorId, setVendorId] = useState("");
  const [productId, setProductId] = useState("");
  const [question, setQuestion] = useState("");
  const [submittedQuestion, setSubmittedQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let mounted = true;
    backendGet<Session>("/api/v1/auth/me")
      .then((current) => {
        if (!mounted) return;
        setSession(current);
        setVendorId(current.vendors[0]?.vendorId ?? "");
      })
      .catch((reason: unknown) => {
        if (mounted && !(reason instanceof BackendRequestError && reason.status === 401)) {
          setError(errorMessage(reason));
        }
      })
      .finally(() => {
        if (mounted) setCheckingSession(false);
      });
    return () => { mounted = false; };
  }, []);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await backendPost<{ userId: string }>("/api/v1/auth/login", { email, password });
      const current = await backendGet<Session>("/api/v1/auth/me");
      setSession(current);
      setVendorId(current.vendors[0]?.vendorId ?? "");
      setPassword("");
    } catch (reason) {
      setError(errorMessage(reason));
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    setBusy(true);
    setError("");
    try {
      await backendPost<void>("/api/v1/auth/logout");
      setSession(null);
      setAnswer(null);
      setProductId("");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function ask(text: string) {
    if (!vendorId || !text.trim() || busy) return;
    setBusy(true);
    setError("");
    setAnswer(null);
    setSubmittedQuestion(text.trim());
    try {
      const result = await backendPost<Answer>(
        `/api/v1/vendors/${encodeURIComponent(vendorId)}/assistant/queries`,
        { question: text.trim(), ...(productId ? { productId } : {}) },
      );
      setAnswer(result);
      setQuestion("");
    } catch (reason) {
      if (reason instanceof BackendRequestError && reason.status === 401) {
        setSession(null);
        setVendorId("");
        setProductId("");
      }
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  function changeVendor(id: string) {
    setVendorId(id);
    setProductId("");
    setAnswer(null);
    setError("");
  }

  return (
    <main className={styles.page}>
      <VendorHeader />
      <section className={styles.panel} aria-labelledby="assistant-title">
        <div className={styles.header}>
          <div>
            <p className={styles.eyebrow}>Vendor workspace</p>
            <h1 id="assistant-title">Ask Sahulat Assistant</h1>
            <p className={styles.subtle}>Clear answers from your current catalog, listings, and stock records.</p>
          </div>
          {session && <button className={styles.quietButton} onClick={logout} disabled={busy}>Sign out</button>}
        </div>

        {checkingSession ? <p role="status">Checking your session…</p> : !session ? (
          <form className={styles.login} onSubmit={login}>
            <h2>Vendor sign in</h2>
            <label>Email<input type="email" autoComplete="username" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} /></label>
            <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
            <button className={styles.primaryButton} type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
            <Link href="/vendor/register">Register a vendor account</Link>
          </form>
        ) : session.vendors.length === 0 ? (
          <p>Your account has no active vendor membership. Contact your vendor administrator.</p>
        ) : (
          <div className={styles.workspace}>
            <label className={styles.vendorSelect}>Vendor
              <select value={vendorId} onChange={(event) => changeVendor(event.target.value)}>
                {session.vendors.map((vendor) => <option key={vendor.vendorId} value={vendor.vendorId}>{vendor.displayName}</option>)}
              </select>
            </label>

            <div className={styles.promptSection}>
              <h2>Try a question</h2>
              <div className={styles.prompts}>
                {prompts.map((prompt) => <button key={prompt} className={styles.prompt} disabled={busy} onClick={() => ask(prompt)}>{prompt}</button>)}
                <button className={styles.prompt} disabled={busy || !productId} onClick={() => ask("Why can't this product be published?")}>Why can&apos;t this product be published?</button>
              </div>
              <p className={styles.hint}>To check publication, first choose a product from an answer&apos;s sources below.</p>
            </div>

            <form className={styles.askForm} onSubmit={(event) => { event.preventDefault(); void ask(question); }}>
              <label htmlFor="assistant-question">Your question</label>
              <div className={styles.askRow}>
                <input id="assistant-question" maxLength={500} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about your catalog" />
                <button className={styles.primaryButton} type="submit" disabled={busy || !question.trim()}>{busy ? "Checking…" : "Ask"}</button>
              </div>
            </form>

            {busy && <p className={styles.loading} role="status">Checking your vendor records…</p>}
            {productId && <p className={styles.selectedProduct}>Selected product: {productId} <button className={styles.quietButton} onClick={() => setProductId("")}>Clear</button></p>}
            {answer && <section className={styles.answer} aria-live="polite">
              <p className={styles.answerLabel}>Assistant answer · {answer.outcome.replaceAll("_", " ")}</p>
              <h2>{submittedQuestion}</h2>
              <p>{answer.answer}</p>
              {answer.evidence.length > 0 && <div>
                <h2>Sources checked</h2>
                <ul>
                  {answer.evidence.map((source) => <li key={`${source.entityType}-${source.entityId}`}>
                    <span>{source.label} · {source.entityType} · {new Date(source.observedAt).toLocaleString()}<br /><code>{source.entityId}</code></span>
                    <span>
                      <Link className={styles.quietButton} href={`/vendor/${encodeURIComponent(vendorId)}/products/${encodeURIComponent(source.productId)}`}>Open product</Link>
                      <button className={styles.quietButton} onClick={() => setProductId(source.productId)}>Select product</button>
                    </span>
                  </li>)}
                </ul>
              </div>}
            </section>}
          </div>
        )}
        {error && <p className={styles.error} role="alert">{error}</p>}
      </section>
    </main>
  );
}
