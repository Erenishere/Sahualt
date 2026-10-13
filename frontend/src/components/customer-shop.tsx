"use client";
/* eslint-disable @next/next/no-img-element */
import Image from "next/image";
import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { SahulatBrand } from "@/components/sahulat-brand";
import type { CheckoutDraft, OfferRecord, OrderRecord, PublicProductDetails, PublicProductSummary } from "@/types/marketplace";
import { notFound } from "next/navigation";
import { useSession } from "@/context/session-context";
import { BackendRequestError } from "@/services/backend-client";
import {
  acceptCounterOffer,
  catalogImageUrl,
  clearCheckoutDraft,
  createOffer,
  formatMoney,
  formatOfferStatus,
  formatOrderStatus,
  getOffer,
  getProduct,
  getProfile,
  listOffers,
  listOrders,
  placeOrder,
  productImageUrl,
  readCheckoutDraft,
  registerCustomer,
  saveCheckoutDraft,
  searchCatalog,
  searchCatalogImage,
  searchCatalogVoice,
  type CatalogSearchPage,
  updateProfile,
  withdrawOffer,
  CHECKOUT_IDEMPOTENCY_KEY,
} from "@/services/marketplace-api";

function go(path: string) {
  if (path.startsWith("/vendor") || path.startsWith("/admin")) {
    location.assign(path);
    return;
  }
  history.pushState({}, "", path);
  dispatchEvent(new PopStateEvent("popstate"));
  scrollTo(0, 0);
}

function usePath(initialPath: string) {
  const [path, setPath] = useState(initialPath);
  useEffect(() => {
    const sync = () => setPath(location.pathname + location.search);
    sync();
    addEventListener("popstate", sync);
    return () => removeEventListener("popstate", sync);
  }, []);
  return path;
}

function errorMessage(error: unknown): string {
  return error instanceof BackendRequestError ? error.message : "Something went wrong. Please try again.";
}

const SEARCH_CACHE_KEY = "sahulat-search-cache";

function readSearchCache(): CatalogSearchPage | null {
  try {
    return JSON.parse(sessionStorage.getItem(SEARCH_CACHE_KEY) || "null") as CatalogSearchPage | null;
  } catch {
    return null;
  }
}

function writeSearchCache(page: CatalogSearchPage) {
  sessionStorage.setItem(SEARCH_CACHE_KEY, JSON.stringify(page));
}

const Status = ({ label }: { label: string }) => (
  <span className={`status ${label.toLowerCase().replaceAll(" ", "-")}`}>{label}</span>
);

function Logo() {
  return <SahulatBrand className="logo" onClick={() => go("/")} />;
}

function NavSearch() {
  const [query, setQuery] = useState("");

  return (
    <form
      className="nav-search"
      aria-label="Search the marketplace"
      onSubmit={(event) => {
        event.preventDefault();
        go(`/search?q=${encodeURIComponent(query.trim())}&mode=text`);
      }}
    >
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <circle cx="11" cy="11" r="6.5" />
        <path d="m16 16 4 4" />
      </svg>
      <label className="sr-only" htmlFor="nav-catalog-search">Search products</label>
      <input
        id="nav-catalog-search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search products, brands or ask anything..."
      />
    </form>
  );
}

function Nav() {
  const { session, loading } = useSession();
  const [open, setOpen] = useState(false);
  const vendorHref = session?.vendors[0]
    ? `/vendor/catalog`
    : "/vendor";

  return (
    <header className="nav marketplace-nav">
      <Logo />
      <nav id="marketplace-menu" className={open ? "open" : ""} aria-label="Marketplace navigation">
        <button type="button" onClick={() => { go("/"); setOpen(false); }}>Shop</button>
        <button type="button" onClick={() => { go("/offers"); setOpen(false); }}>My Offers</button>
        <button type="button" onClick={() => { go("/orders"); setOpen(false); }}>My Orders</button>
        <button type="button" onClick={() => { go(vendorHref); setOpen(false); }}>For Vendors</button>
        {!loading && !session && (
          <button className="nav-menu-sign-in" type="button" onClick={() => { go("/login"); setOpen(false); }}>Sign In</button>
        )}
      </nav>
      <NavSearch />
      <button className="nav-icon nav-cart" type="button" onClick={() => go("/orders")} aria-label="View orders">
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path d="M3.5 4.5h2l1.7 10.2h10.9l1.7-7.4H7" />
          <circle cx="9" cy="19" r="1.25" />
          <circle cx="17" cy="19" r="1.25" />
        </svg>
      </button>
      <button className="nav-icon nav-account" type="button" onClick={() => go(session ? "/profile" : "/login")} aria-label="Account">
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <circle cx="12" cy="8" r="3.5" />
          <path d="M5.5 20a6.5 6.5 0 0 1 13 0" />
        </svg>
      </button>
      {!loading && !session ? (
        <button className="nav-sign-in" type="button" onClick={() => go("/login")}>Sign In</button>
      ) : session ? (
        <button className="nav-user" type="button" onClick={() => go("/profile")} aria-label="Open profile">AU</button>
      ) : null}
      <button className="mobile-menu" type="button" onClick={() => setOpen(!open)} aria-label={open ? "Close navigation" : "Open navigation"} aria-controls="marketplace-menu" aria-expanded={open}>
        <svg aria-hidden="true" viewBox="0 0 24 24">
          {open ? <path d="m6 6 12 12M18 6 6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
        </svg>
      </button>
    </header>
  );
}

function CustomerNotice({ title, description, actionLabel, actionPath }: {
  title: string;
  description: string;
  actionLabel?: string;
  actionPath?: string;
}) {
  return <>
    <Nav />
    <main className="customer-notice-page">
      <section className="customer-notice">
        <p className="customer-notice-eyebrow">Sahulat AI marketplace</p>
        <h1>{title}</h1>
        <p>{description}</p>
        <div className="customer-notice-actions">
          {actionLabel && actionPath && <button type="button" className="primary" onClick={() => go(actionPath)}>{actionLabel}</button>}
          <button type="button" onClick={() => go("/")}>Back to shop</button>
        </div>
      </section>
    </main>
  </>;
}

function SearchBar({
  big = false,
  onImage,
  onVoice,
  initialQuery = "",
}: {
  big?: boolean;
  onImage?: () => void;
  onVoice?: () => void;
  initialQuery?: string;
}) {
  const [query, setQuery] = useState(initialQuery);
  return (
    <form
      className={`search ${big ? "big" : ""}`}
      aria-label="Search the product catalog"
      onSubmit={(e) => {
        e.preventDefault();
        go(`/search?q=${encodeURIComponent(query.trim())}&mode=text`);
      }}
    >
      <div className="search-field">
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <circle cx="11" cy="11" r="6.5" />
          <path d="m16 16 4 4" />
        </svg>
        <label className="sr-only" htmlFor="catalog-search">Search products</label>
        <input
          id="catalog-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Try ‘black embroidered kurta under 5,000’"
          aria-label="Search products"
          dir="auto"
        />
        {query && <button className="search-clear" type="button" onClick={() => setQuery("")}>Clear</button>}
      </div>
      <button className="search-mode" type="button" onClick={onVoice} disabled={!onVoice} aria-label="Search by voice" title="Search by voice">
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <rect x="9" y="3" width="6" height="11" rx="3" />
          <path d="M6.5 11.5a5.5 5.5 0 0 0 11 0M12 17v4m-3 0h6" />
        </svg>
        <span>Voice</span>
      </button>
      <button className="search-mode" type="button" onClick={onImage} disabled={!onImage} aria-label="Search by image" title="Search by image">
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <circle cx="9" cy="10" r="2" />
          <path d="m5 17 4-4 3 3 2-2 5 3" />
        </svg>
        <span>Image</span>
      </button>
      <button className="primary" type="submit">Search</button>
    </form>
  );
}

function availabilityLabel(product: PublicProductSummary): string {
  if (product.availableStock === null) return "Stock unknown";
  if (product.availableStock === 0) return "Out of stock";
  if (product.availableStock <= 5) return "Low stock";
  return "Available";
}

function ProductCards({ items }: { items: PublicProductSummary[] }) {
  return (
    <div className="cards">
      {items.map((product) => (
        <article
          className="card"
          key={product.productId}
          role="link"
          tabIndex={0}
          onClick={() => go(`/product/${product.productId}`)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              go(`/product/${product.productId}`);
            }
          }}
        >
          <div>
            <img src={productImageUrl(product)} alt={product.name} />
          </div>
          <small>{product.vendorName}</small>
          <h3>{product.name}</h3>
          <b>{formatMoney(product.startingPrice, product.currency)}</b>
          <span>{availabilityLabel(product)}</span>
          <em>View Product →</em>
        </article>
      ))}
    </div>
  );
}

function Section({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  return (
    <section className="section">
      <div className="section-title"><div><h2>{title}</h2>{sub && <p>{sub}</p>}</div></div>
      {children}
    </section>
  );
}

function DiscoveryModal({ type, close }: { type: "image" | "voice"; close: () => void }) {
  const [preview, setPreview] = useState<string | null>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const audioInput = useRef<HTMLInputElement>(null);

  function loadImage(file?: File) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Choose an image file to continue.");
      return;
    }
    setImageFile(file);
    const reader = new FileReader();
    reader.onload = () => { setPreview(String(reader.result)); setError(""); };
    reader.onerror = () => setError("Image upload failed. Please try another file.");
    reader.readAsDataURL(file);
  }

  async function runImageSearch() {
    if (!imageFile) {
      setError("Upload an image first.");
      return;
    }
    setBusy(true);
    try {
      const page = await searchCatalogImage(imageFile);
      writeSearchCache(page);
      go("/search?mode=image");
      close();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function runVoiceSearch() {
    if (!audioFile) {
      setError("Upload a WAV recording first.");
      return;
    }
    setBusy(true);
    try {
      const page = await searchCatalogVoice(audioFile);
      writeSearchCache(page);
      go(`/search?q=${encodeURIComponent(page.query ?? "voice")}&mode=voice`);
      close();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  function loadAudio(file?: File) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".wav")) {
      setAudioFile(null);
      setError("Choose a WAV file (.wav) to continue.");
      if (audioInput.current) audioInput.current.value = "";
      return;
    }
    setAudioFile(file);
    setError("");
  }

  return (
    <div className="backdrop" onMouseDown={close}>
      <div className="modal" role="dialog" aria-modal="true" onMouseDown={(e) => e.stopPropagation()}>
        <button className="x" type="button" onClick={close} aria-label="Close">×</button>
        <p className="eyebrow">{type === "image" ? "VISUAL DISCOVERY" : "VOICE DISCOVERY"}</p>
        <h2>{type === "image" ? "Search by Image" : "Search with your voice"}</h2>
        {type === "image" ? (
          <>
            <div className="drop" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); loadImage(e.dataTransfer.files[0]); }}>
              {preview ? <img className="upload-image" src={preview} alt="Uploaded preview" /> : <><span>▧</span><b>Drop an image here</b></>}
              <button type="button" onClick={() => fileInput.current?.click()}>Browse Image</button>
              <input ref={fileInput} type="file" accept="image/*" hidden onChange={(e) => loadImage(e.target.files?.[0])} />
            </div>
            <button className="primary wide" type="button" disabled={busy} onClick={runImageSearch}>
              {busy ? "Searching…" : "Find similar products"}
            </button>
          </>
        ) : (
          <>
            <p className="demo-note">Upload a short WAV clip (English or Urdu).</p>
            <button type="button" onClick={() => audioInput.current?.click()}>Choose WAV file</button>
            <input ref={audioInput} type="file" accept=".wav,audio/wav,audio/x-wav" hidden onChange={(e) => loadAudio(e.target.files?.[0])} />
            <p className="demo-note" role="status" aria-live="polite">
              {audioFile ? `Selected: ${audioFile.name}` : "No WAV recording selected yet."}
            </p>
            <button className="primary wide" type="button" disabled={busy || !audioFile} onClick={runVoiceSearch}>
              {busy ? "Transcribing…" : "Search by voice"}
            </button>
          </>
        )}
        {error && <p className="error-state" role="alert">{error}</p>}
      </div>
    </div>
  );
}

type HomeCategoryArt = "women" | "men" | "footwear" | "jewellery" | "beauty" | "home" | "electronics";

const NON_PRODUCTION_CATALOG_TEXT = /\b(?:test|staging|fixture|seed)\b/i;

function isEligibleHomepageProduct(product: PublicProductSummary): boolean {
  const searchableText = `${product.name} ${product.vendorName} ${product.vendorSlug}`;
  return Boolean(
    product.primaryImageId &&
    product.name.trim() &&
    product.vendorName.trim() &&
    product.vendorSlug.trim() &&
    product.currency.trim() &&
    Number.isFinite(product.startingPrice) &&
    product.startingPrice > 0 &&
    !NON_PRODUCTION_CATALOG_TEXT.test(searchableText)
  );
}

function categoryArtFor(label: string, index: number): HomeCategoryArt {
  const normalized = label.toLowerCase();
  if (/women|ladies|lawn|dress|fashion/.test(normalized)) return "women";
  if (/men|kurta|menswear/.test(normalized)) return "men";
  if (/shoe|footwear|bag/.test(normalized)) return "footwear";
  if (/jewel|accessor/.test(normalized)) return "jewellery";
  if (/beauty|care|cosmetic/.test(normalized)) return "beauty";
  if (/home|living|decor/.test(normalized)) return "home";
  if (/electronic|gadget|phone|audio/.test(normalized)) return "electronics";
  return (["home", "electronics", "beauty", "footwear", "jewellery", "women", "men"] as const)[index % 7];
}

function FeatureIcon({ name }: { name: "spark" | "store" | "shield" | "delivery" }) {
  if (name === "spark") {
    return <svg aria-hidden="true" viewBox="0 0 32 32"><path d="M16 3l2.6 7.4L26 13l-7.4 2.6L16 23l-2.6-7.4L6 13l7.4-2.6L16 3Z" /><path d="m25 20 1.2 3.3 3.3 1.2-3.3 1.2L25 29l-1.2-3.3-3.3-1.2 3.3-1.2L25 20Z" /></svg>;
  }
  if (name === "store") {
    return <svg aria-hidden="true" viewBox="0 0 32 32"><path d="M6 13h20v14H6zM4 10l3-6h18l3 6-2 4H6l-2-4Z" /><path d="M12 27v-8h8v8M10 10v4m6-4v4m6-4v4" /></svg>;
  }
  if (name === "shield") {
    return <svg aria-hidden="true" viewBox="0 0 32 32"><path d="M16 3 26 7v8c0 6.5-4.2 11.2-10 14-5.8-2.8-10-7.5-10-14V7l10-4Z" /><path d="m11 16 3.2 3.2L21 12.5" /></svg>;
  }
  return <svg aria-hidden="true" viewBox="0 0 32 32"><path d="M4 7h15v15H4zM19 12h5l4 5v5h-9z" /><circle cx="10" cy="24" r="3" /><circle cx="24" cy="24" r="3" /></svg>;
}

function CategoryArtwork({ art, product }: { art: HomeCategoryArt; product: PublicProductSummary }) {
  if (product.primaryImageId) return <img src={productImageUrl(product)} alt="" />;
  if (art === "footwear") {
    return <svg aria-hidden="true" viewBox="0 0 150 110"><path d="M16 80c18-3 29-13 40-34 3-6 10-8 16-4l24 17c8 6 19 9 31 10 7 1 11 5 11 11H16Z" /><path d="M91 36h33v38M96 36v-9c0-8 6-14 14-14s14 6 14 14v9" /><path d="M26 73c16-2 25-11 34-29" /></svg>;
  }
  if (art === "jewellery") {
    return <svg aria-hidden="true" viewBox="0 0 150 110"><path d="M48 12v19m54-19v19" /><circle cx="48" cy="39" r="10" /><circle cx="102" cy="39" r="10" /><path d="M38 47 24 83l24 15 24-15-14-36M92 47 78 83l24 15 24-15-14-36" /><path d="m24 83 24-5 24 5m6 0 24-5 24 5" /></svg>;
  }
  if (art === "beauty") {
    return <svg aria-hidden="true" viewBox="0 0 150 110"><path d="M18 39h31l-4 57H22l-4-57Z" /><path d="M26 29h15v10M65 21h27v75H65zM72 13h13v8M106 48h26v48h-26zM112 36h14v12" /><path d="M23 65c10 5 17 5 23 0" /></svg>;
  }
  if (art === "home") {
    return <svg aria-hidden="true" viewBox="0 0 150 110"><path d="M34 78h86v7H34zM43 85v13m68-13v13" /><path d="M55 51h34l-4 27H59l-4-27Z" /><path d="M72 52c-1-17-12-26-24-30 1 13 8 25 24 30Zm2-1c6-17 18-24 31-23-5 15-15 24-31 23Zm0 1c-11-10-12-23-7-34 10 9 14 20 7 34Z" /></svg>;
  }
  return <svg aria-hidden="true" viewBox="0 0 150 110"><rect x="25" y="42" width="35" height="56" rx="5" /><path d="M32 50h21M39 90h7" /><path d="M82 78V49c0-18 12-32 28-32s28 14 28 32v29" /><rect x="76" y="67" width="15" height="28" rx="7" /><rect x="129" y="67" width="15" height="28" rx="7" /></svg>;
}

function HomePage() {
  const [modal, setModal] = useState<"image" | "voice" | null>(null);
  const [featured, setFeatured] = useState<PublicProductSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [requestVersion, setRequestVersion] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    searchCatalog({ limit: 24 })
      .then((page) => {
        if (active) setFeatured(page.items.filter(isEligibleHomepageProduct).slice(0, 8));
      })
      .catch((reason) => {
        if (active) {
          setFeatured([]);
          setError(errorMessage(reason));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [requestVersion]);

  const vendors = [...new Map(featured.map((product) => [product.vendorSlug, product])).values()].slice(0, 3);
  const heroProduct = featured[0];
  const examples = ["Wireless headphones", "Home office lamp", "عید کا لباس", "Skin care gift set", "Everyday sneakers"];
  const categories = [...new Map(
    featured
      .filter((product) => product.category?.trim())
      .map((product) => [product.category!.trim(), product]),
  ).entries()].slice(0, 7);

  return (
    <>
      <Nav />
      <main className="customer-home">
        <section className="home-hero">
          <div className="home-hero-copy">
            <p className="eyebrow">PAKISTAN&apos;S AI-POWERED MARKETPLACE</p>
            <h1><span>Dhoondo,</span><br /><i>apne andaaz mein.</i></h1>
            <p className="home-lede">Search your way — type it, show it, or say it. Discover products from local vendors with Sahulat AI.</p>
            <SearchBar big onImage={() => setModal("image")} onVoice={() => setModal("voice")} />
            <div className="chips" aria-label="Example searches">
              <span>TRY</span>
              {examples.map((example) => (
                <button key={example} type="button" dir="auto" onClick={() => go(`/search?q=${encodeURIComponent(example)}&mode=text`)}>{example}</button>
              ))}
            </div>
            <div className="home-features" aria-label="Marketplace benefits">
              <article><span><FeatureIcon name="spark" /></span><div><b>Multimodal Search</b><small>Text, image or voice</small></div></article>
              <article><span><FeatureIcon name="store" /></span><div><b>Local Vendors</b><small>Published marketplace catalog</small></div></article>
              <article><span><FeatureIcon name="shield" /></span><div><b>Clear Details</b><small>Prices and stock information</small></div></article>
              <article><span><FeatureIcon name="delivery" /></span><div><b>Offer Ready</b><small>Where vendors enable offers</small></div></article>
            </div>
          </div>
          <div className="home-hero-visual">
            <div className="hero-photo">
              <Image
                src="/home/hero-editorial.webp"
                alt="Editorial image of a woman wearing a black embroidered Pakistani outfit"
                fill
                priority
                sizes="(min-width: 1280px) 42vw, (min-width: 769px) 45vw, 100vw"
              />
            </div>
            <div className="hero-accent" aria-hidden="true">
              <svg viewBox="0 0 76 76">
                <circle cx="31" cy="31" r="18" />
                <path d="m44 44 13 13M9 31h7M31 9v7" />
                <path d="m61 14 1.8 5.2L68 21l-5.2 1.8L61 28l-1.8-5.2L54 21l5.2-1.8L61 14Z" />
              </svg>
            </div>
            {featured.length > 1 && (
              <div className="hero-thumbnails" aria-label="Featured products">
                {featured.slice(0, 3).map((product, index) => (
                  <button className={index === 0 ? "active" : undefined} key={product.productId} type="button" onClick={() => go(`/product/${product.productId}`)} aria-label={`View ${product.name}`}>
                    <img src={productImageUrl(product)} alt="" />
                  </button>
                ))}
              </div>
            )}
            {heroProduct && (
              <button className="hero-product-card" type="button" onClick={() => go(`/product/${heroProduct.productId}`)} aria-label={`View ${heroProduct.name} from ${heroProduct.vendorName}`}>
                <img src={productImageUrl(heroProduct)} alt={heroProduct.name} />
                <span className="hero-product-copy">
                  <small>{heroProduct.vendorName}</small>
                  <strong>{heroProduct.name}</strong>
                  <b>{formatMoney(heroProduct.startingPrice, heroProduct.currency)}</b>
                  <em>{availabilityLabel(heroProduct)}</em>
                </span>
                <span className="hero-product-arrow" aria-hidden="true">→</span>
              </button>
            )}
          </div>
        </section>

        <section className="home-category-section" aria-labelledby="home-category-title">
          <header>
            <h2 id="home-category-title">Shop by Category</h2>
            <button type="button" onClick={() => go("/search")}>View All Categories <span aria-hidden="true">→</span></button>
          </header>
          {loading ? (
            <div className="category-skeletons" role="status"><span className="sr-only">Loading categories…</span><i /><i /><i /><i /></div>
          ) : error ? (
            <div className="home-section-state" role="alert"><p>Categories are unavailable right now.</p><button type="button" onClick={() => setRequestVersion((version) => version + 1)}>Try again</button></div>
          ) : categories.length ? (
            <div className="home-categories">
              {categories.map(([category, product], index) => {
                const art = categoryArtFor(category, index);
                return (
                  <button key={category} type="button" onClick={() => go(`/search?category=${encodeURIComponent(category)}&mode=text`)}>
                    <span className="category-label">{category}</span>
                    <span className={`category-art category-art-${art}`}><CategoryArtwork art={art} product={product} /></span>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="home-section-state"><p>Categories will appear when eligible products are published.</p><button type="button" onClick={() => go("/search")}>Browse the catalog</button></div>
          )}
        </section>

        <Section title="Featured Products" sub="Published products from marketplace vendors">
          {loading ? (
            <div className="product-skeletons" role="status"><span className="sr-only">Loading products…</span><i /><i /><i /><i /></div>
          ) : error ? (
            <div className="catalog-state" role="alert">
              <h3>We couldn’t load the catalog.</h3>
              <p>{error}</p>
              <button type="button" onClick={() => setRequestVersion((version) => version + 1)}>Try again</button>
            </div>
          ) : featured.length ? (
            <ProductCards items={featured} />
          ) : (
            <div className="catalog-state">
              <h3>No published products yet.</h3>
              <p>Check back when vendors have published their listings.</p>
            </div>
          )}
        </Section>

        {vendors.length > 0 && (
          <Section title="Featured Vendors" sub="Stores represented in the published catalog">
            <div className="vendors">
              {vendors.map((vendor) => (
                <article key={vendor.vendorSlug}>
                  <img src={productImageUrl(vendor)} alt="" />
                  <div>
                    <small>FEATURED STORE</small>
                    <h3>{vendor.vendorName}</h3>
                    <p>{vendor.category ?? "Published marketplace products"}</p>
                    <button type="button" onClick={() => go(`/shop/${vendor.vendorSlug}`)}>View Store →</button>
                  </div>
                </article>
              ))}
            </div>
          </Section>
        )}

        <section className="vendor-onboarding" aria-labelledby="vendor-onboarding-title">
          <div>
            <p className="eyebrow">FOR LOCAL VENDORS</p>
            <h2 id="vendor-onboarding-title">Bring your catalog to Sahulat.</h2>
            <p>Manage products, listings, availability and stock from the vendor workspace.</p>
          </div>
          <button type="button" onClick={() => go("/vendor")}>Explore Vendor Tools <span aria-hidden="true">→</span></button>
        </section>

        <section className="how-it-works" aria-labelledby="how-it-works-title">
          <div>
            <p className="eyebrow">A SIMPLE WAY TO SHOP</p>
            <h2 id="how-it-works-title">From an idea to the right product.</h2>
            <p>Search the catalog, compare the details, then decide whether to buy or start an offer yourself.</p>
          </div>
          <ol>
            <li><span>01</span><div><b>Describe it</b><p>Type your request, upload a reference image, or add a voice recording.</p></div></li>
            <li><span>02</span><div><b>Explore matches</b><p>Review catalog products, prices, variants, and available stock information.</p></div></li>
            <li><span>03</span><div><b>Make your offer</b><p>Open a product and submit an offer manually when that vendor allows it.</p></div></li>
          </ol>
        </section>
      </main>
      <footer><Logo /><p>Discover local style with text, image or voice.</p><span>© 2026 Sahulat AI</span></footer>
      {modal && <DiscoveryModal type={modal} close={() => setModal(null)} />}
    </>
  );
}

function SearchPage({ query, mode, initialCategory = "" }: { query: string; mode: string; initialCategory?: string }) {
  const [modal, setModal] = useState<"image" | "voice" | null>(null);
  const [category, setCategory] = useState(initialCategory);
  const [items, setItems] = useState<PublicProductSummary[]>([]);
  const [searchMode, setSearchMode] = useState(mode);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    const cached = mode === "image" || mode === "voice" ? readSearchCache() : null;
    if (cached && (mode === "image" || mode === "voice")) {
      setItems(cached.items);
      setSearchMode(cached.mode);
      setError("");
      setLoading(false);
      return;
    }
    const apiMode = mode;
    searchCatalog({ query: query || undefined, category: category || undefined, limit: 50, mode: apiMode })
      .then((page) => {
        setItems(page.items);
        setSearchMode("mode" in page ? page.mode : apiMode);
        setError("");
      })
      .catch((reason) => setError(errorMessage(reason)))
      .finally(() => setLoading(false));
  }, [query, category, mode]);

  const categories = [...new Set(items.map((p) => p.category).filter(Boolean))] as string[];

  return (
    <>
      <Nav />
      <main className="page">
        <SearchBar initialQuery={query} onImage={() => setModal("image")} onVoice={() => setModal("voice")} />
        <div className="title-row">
          <div>
            <Status label={`${searchMode.replace("-", " + ")} search`} />
            <h1>{query || "All products"}</h1>
            <p>{loading ? "Searching…" : `${items.length} products`}</p>
          </div>
        </div>
        {error && <p className="error-state" role="alert">{error}</p>}
        <div className="results">
          <aside>
            <h3>Filters</h3>
            <label className="field">
              <span>Category</span>
              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">All categories</option>
                {categories.map((x) => <option key={x} value={x}>{x}</option>)}
              </select>
            </label>
          </aside>
          <div>
            {!loading && items.length ? <ProductCards items={items} /> : !loading && (
              <div className="empty-state"><h2>No matching products</h2><p>Try another search term.</p></div>
            )}
          </div>
        </div>
      </main>
      {modal && <DiscoveryModal type={modal} close={() => setModal(null)} />}
    </>
  );
}

function StorePage({ slug }: { slug: string }) {
  const [items, setItems] = useState<PublicProductSummary[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    searchCatalog({ vendor: slug, limit: 50 })
      .then((page) => setItems(page.items))
      .catch((reason) => setError(errorMessage(reason)));
  }, [slug]);

  const storeName = items[0]?.vendorName ?? slug;
  const visible = items.filter((p) => p.name.toLowerCase().includes(query.toLowerCase()));

  return (
    <>
      <Nav />
      <section className="store">
        <img src={items[0] ? productImageUrl(items[0]) : "/products/midnight-kurta.svg"} alt="Store" />
        <div>
          <p className="eyebrow">VENDOR STOREFRONT</p>
          <h1>{storeName}</h1>
          <b>{items.length} products</b>
        </div>
      </section>
      <main className="page">
        {error && <p className="error-state" role="alert">{error}</p>}
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={`Search within ${storeName}`} aria-label="Search store" />
        {visible.length ? <ProductCards items={visible} /> : <div className="empty-state"><h2>No products</h2></div>}
      </main>
    </>
  );
}

function OfferModal({
  product,
  listing,
  close,
}: {
  product: PublicProductDetails;
  listing: PublicProductDetails["listings"][number];
  close: () => void;
}) {
  const { session } = useSession();
  const [amount, setAmount] = useState(String(Math.round(listing.price * 0.9)));
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!session) {
      go("/login");
      return;
    }
    const value = Number(amount);
    if (!Number.isFinite(value) || value <= 0 || value >= listing.price) {
      setError("Enter a valid offer below the listed price.");
      return;
    }
    setBusy(true);
    try {
      const offer = await createOffer(listing.listingId, value, message);
      close();
      go(`/offers/${offer.offerId}`);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="backdrop" onMouseDown={close}>
      <aside className="drawer" role="dialog" aria-modal="true" onMouseDown={(e) => e.stopPropagation()}>
        <button className="x" type="button" onClick={close} aria-label="Close">×</button>
        <h2>Make an Offer</h2>
        <div className="mini-product">
          <img src={product.primaryImageId ? catalogImageUrl(product.productId, product.primaryImageId) : "/products/midnight-kurta.svg"} alt={product.name} />
          <b>{product.name}<small>{product.vendorName}</small></b>
        </div>
        <p className="line">Listed Price <b>{formatMoney(listing.price, listing.currency)}</b></p>
        <label className="field"><span>Your Offer</span><input type="number" min={1} max={listing.price - 1} value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
        <label className="field"><span>Message — optional</span><textarea value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Short note for the vendor" /></label>
        {error && <p className="error-state" role="alert">{error}</p>}
        <button className="primary wide" type="button" disabled={busy} onClick={submit}>{busy ? "Submitting…" : "Submit Offer"}</button>
      </aside>
    </div>
  );
}

function ProductPage({ productId }: { productId: string }) {
  const { session } = useSession();
  const [product, setProduct] = useState<PublicProductDetails | null>(null);
  const [listingIndex, setListingIndex] = useState(0);
  const [quantity, setQuantity] = useState(1);
  const [offerOpen, setOfferOpen] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getProduct(productId)
      .then((details) => { setProduct(details); setListingIndex(0); })
      .catch((reason) => setError(errorMessage(reason)))
      .finally(() => setLoading(false));
  }, [productId]);

  if (loading) return <><Nav /><main className="page"><p role="status">Loading product…</p></main></>;
  if (!product) return <><Nav /><main className="page"><h1>Product not found</h1></main></>;

  const listing = product.listings[listingIndex] ?? product.listings[0];
  if (!listing) {
    return <><Nav /><main className="page"><h1>No active listings</h1></main></>;
  }

  const maxQty = listing.availableStock ?? 10;

  function startCheckout(acceptedOfferId?: string) {
    if (!session) {
      go("/login");
      return;
    }
    if (!product) return;
    const draft: CheckoutDraft = {
      listingId: listing.listingId,
      productId: product.productId,
      productName: product.name,
      vendorName: product.vendorName,
      unitPrice: listing.price,
      currency: listing.currency,
      quantity,
      imageUrl: product.primaryImageId ? catalogImageUrl(product.productId, product.primaryImageId) : undefined,
      acceptedOfferId,
    };
    saveCheckoutDraft(draft);
    go("/checkout");
  }

  return (
    <>
      <Nav />
      <main className="page">
        <section className="product">
          <div className="gallery">
            <img
              src={product.primaryImageId ? catalogImageUrl(product.productId, product.primaryImageId) : "/products/midnight-kurta.svg"}
              alt={product.name}
            />
          </div>
          <div className="product-copy">
            <button className="seller-link" type="button" onClick={() => go(`/shop/${product.vendorSlug}`)}>{product.vendorName} →</button>
            <h1>{product.name}</h1>
            <b className="big-price">{formatMoney(listing.price, listing.currency)}</b>
            <p>{product.description}</p>
            {product.listings.length > 1 && (
              <label>
                Variant
                <div className="choices">
                  {product.listings.map((row, index) => (
                    <button key={row.listingId} type="button" className={index === listingIndex ? "on" : ""} onClick={() => setListingIndex(index)}>
                      {[row.color, row.size, row.variantCode].filter(Boolean).join(" · ")}
                    </button>
                  ))}
                </div>
              </label>
            )}
            <label>
              Quantity
              <div className="choices">
                <button type="button" onClick={() => setQuantity(Math.max(1, quantity - 1))}>−</button>
                <button type="button">{quantity}</button>
                <button type="button" onClick={() => setQuantity(Math.min(maxQty, quantity + 1))}>+</button>
              </div>
            </label>
            <button className="primary" type="button" onClick={() => startCheckout()}>Buy now (COD)</button>
            {listing.allowsOffers && (
              <button className="offer" type="button" onClick={() => (session ? setOfferOpen(true) : go("/login"))}>Make an Offer</button>
            )}
          </div>
        </section>
        {error && <p className="error-state" role="alert">{error}</p>}
      </main>
      {offerOpen && <OfferModal product={product} listing={listing} close={() => setOfferOpen(false)} />}
    </>
  );
}

function Tabs({ labels, value, onChange }: { labels: string[]; value: string; onChange: (value: string) => void }) {
  return (
    <div className="tabs">
      {labels.map((label) => (
        <button key={label} type="button" className={value === label ? "on" : ""} onClick={() => onChange(label)}>{label}</button>
      ))}
    </div>
  );
}

function OffersPage({ detail = false, offerId }: { detail?: boolean; offerId?: string }) {
  const { session, loading: sessionLoading } = useSession();
  const [offers, setOffers] = useState<OfferRecord[]>([]);
  const [offer, setOffer] = useState<OfferRecord | null>(null);
  const [tab, setTab] = useState("All");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (sessionLoading) return;
    if (!session) return;
    if (detail && offerId) {
      getOffer(offerId).then(setOffer).catch((reason) => setError(errorMessage(reason)));
      return;
    }
    listOffers()
      .then(setOffers)
      .catch((reason) => setError(errorMessage(reason)));
  }, [session, sessionLoading, detail, offerId]);

  if (!sessionLoading && !session) {
    return <CustomerNotice title="Sign in to view offers" description="Your offers are saved to your account." actionLabel="Sign in" actionPath="/login" />;
  }

  async function acceptCounter(selected: OfferRecord) {
    setBusy(true);
    try {
      await acceptCounterOffer(selected.offerId);
      const draft: CheckoutDraft = {
        listingId: selected.listingId,
        productId: selected.productId,
        productName: selected.productName,
        vendorName: selected.vendorName,
        unitPrice: selected.counterPrice ?? selected.offeredPrice,
        currency: selected.currency,
        quantity: 1,
        acceptedOfferId: selected.offerId,
      };
      saveCheckoutDraft(draft);
      go("/checkout");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  if (detail) {
    if (!offer) return <><Nav /><main className="page narrow"><p role="status">Loading offer…</p></main></>;
    return (
      <>
        <Nav />
        <main className="page narrow">
          <div className="title-row"><h1>{offer.offerNumber}</h1><Status label={formatOfferStatus(offer.status)} /></div>
          <p>Listed: {formatMoney(offer.listedPrice, offer.currency)}</p>
          <p>Your offer: {formatMoney(offer.offeredPrice, offer.currency)}</p>
          {offer.counterPrice != null && <p>Counter: {formatMoney(offer.counterPrice, offer.currency)}</p>}
          {offer.status === "countered" && offer.counterPrice != null && (
            <div className="actions">
              <button type="button" disabled={busy} onClick={() => withdrawOffer(offer.offerId).then(() => getOffer(offer.offerId).then(setOffer))}>Decline</button>
              <button type="button" className="primary" disabled={busy} onClick={() => acceptCounter(offer)}>Accept & checkout</button>
            </div>
          )}
          {error && <p className="error-state" role="alert">{error}</p>}
        </main>
      </>
    );
  }

  const visible = offers.filter((row) => tab === "All" || formatOfferStatus(row.status) === tab);

  return (
    <>
      <Nav />
      <main className="page">
        <h1>My Offers</h1>
        <Tabs labels={["All", "Pending", "Countered", "Accepted", "Rejected"]} value={tab} onChange={setTab} />
        {error && <p className="error-state" role="alert">{error}</p>}
        <div className="offer-list">
          {visible.map((row) => (
            <article key={row.offerId} onClick={() => go(`/offers/${row.offerId}`)} role="link" tabIndex={0}>
              <b>{row.productName}<small>{row.vendorName} · {row.offerNumber}</small></b>
              <p>Listed <strong>{formatMoney(row.listedPrice, row.currency)}</strong></p>
              <p>Offer <strong>{formatMoney(row.offeredPrice, row.currency)}</strong></p>
              <Status label={formatOfferStatus(row.status)} />
            </article>
          ))}
        </div>
      </main>
    </>
  );
}

function CheckoutPage() {
  const { session, loading: sessionLoading } = useSession();
  const draft = readCheckoutDraft();
  const [placed, setPlaced] = useState<OrderRecord | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [addressLine1, setAddressLine1] = useState("");
  const [city, setCity] = useState("");
  const [postalCode, setPostalCode] = useState("");

  useEffect(() => {
    if (!session) return;
    getProfile()
      .then((profile) => {
        setName(profile.displayName);
        setPhone(profile.phone ?? "");
        const address = profile.addresses.find((row) => row.isDefault) ?? profile.addresses[0];
        if (address) {
          setName(address.recipientName);
          setPhone(address.phone);
          setAddressLine1(address.addressLine1);
          setCity(address.city);
          setPostalCode(address.postalCode ?? "");
        }
      })
      .catch(() => undefined);
  }, [session]);

  if (!sessionLoading && !session) {
    return <CustomerNotice title="Sign in to checkout" description="Sign in to place your order and keep track of it." actionLabel="Sign in" actionPath="/login" />;
  }
  if (!draft) {
    return <CustomerNotice title="Your cart is empty" description="Browse the catalog to find something you like." actionLabel="Browse products" actionPath="/search" />;
  }

  const subtotal = draft.unitPrice * draft.quantity;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const cart = readCheckoutDraft();
    if (!cart) return;
    let idempotencyKey = sessionStorage.getItem(CHECKOUT_IDEMPOTENCY_KEY);
    if (!idempotencyKey) {
      idempotencyKey = crypto.randomUUID();
      sessionStorage.setItem(CHECKOUT_IDEMPOTENCY_KEY, idempotencyKey);
    }
    setBusy(true);
    try {
      const order = await placeOrder(cart, { name, phone, addressLine1, city, postalCode }, idempotencyKey);
      clearCheckoutDraft();
      setPlaced(order);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  if (placed) {
    return (
      <>
        <Nav />
        <main className="page narrow">
          <section className="checkout-success">
            <span>✓</span>
            <h1>Order placed</h1>
            <p>Order {placed.orderNumber} was created with cash on delivery.</p>
            <button type="button" className="primary" onClick={() => go("/orders")}>View orders</button>
          </section>
        </main>
      </>
    );
  }

  return (
    <>
      <Nav />
      <main className="page">
        <form className="checkout-page" onSubmit={submit}>
          <div>
            <section className="panel">
              <h2>Delivery</h2>
              <label className="field"><span>Full name</span><input required value={name} onChange={(e) => setName(e.target.value)} /></label>
              <label className="field"><span>Phone</span><input required value={phone} onChange={(e) => setPhone(e.target.value)} /></label>
              <label className="field"><span>Address</span><input required value={addressLine1} onChange={(e) => setAddressLine1(e.target.value)} /></label>
              <label className="field"><span>City</span><input required value={city} onChange={(e) => setCity(e.target.value)} /></label>
              <label className="field"><span>Postal code</span><input value={postalCode} onChange={(e) => setPostalCode(e.target.value)} /></label>
            </section>
            <section className="panel">
              <h2>Payment</h2>
              <p>Cash on delivery</p>
            </section>
          </div>
          <aside className="panel order-summary">
            <h2>Summary</h2>
            <div className="mini-product">
              {draft.imageUrl && <img src={draft.imageUrl} alt="" />}
              <b>{draft.productName}<small>{draft.vendorName} · Qty {draft.quantity}</small></b>
            </div>
            <p className="line order-total">Total <b>{formatMoney(subtotal, draft.currency)}</b></p>
            {error && <p className="error-state" role="alert">{error}</p>}
            <button className="primary wide" type="submit" disabled={busy}>{busy ? "Placing order…" : "Place order"}</button>
          </aside>
        </form>
      </main>
    </>
  );
}

function OrdersPage() {
  const { session, loading: sessionLoading } = useSession();
  const [orders, setOrders] = useState<OrderRecord[]>([]);
  const [tab, setTab] = useState("All");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!session) return;
    listOrders()
      .then(setOrders)
      .catch((reason) => setError(errorMessage(reason)));
  }, [session]);

  if (!sessionLoading && !session) {
    return <CustomerNotice title="Sign in to view orders" description="Your orders and delivery updates are saved to your account." actionLabel="Sign in" actionPath="/login" />;
  }

  const visible = orders.filter((order) => {
    if (tab === "All") return true;
    if (tab === "Processing") return ["placed", "confirmed", "processing", "shipped"].includes(order.status);
    if (tab === "Completed") return order.status === "completed";
    if (tab === "Cancelled") return order.status === "cancelled";
    return true;
  });

  return (
    <>
      <Nav />
      <main className="page">
        <h1>My orders</h1>
        <Tabs labels={["All", "Processing", "Completed", "Cancelled"]} value={tab} onChange={setTab} />
        {error && <p className="error-state" role="alert">{error}</p>}
        <div className="order-cards">
          {visible.map((order) => (
            <article key={order.orderId}>
              <div>
                <small>{order.orderNumber} · {new Date(order.placedAt).toLocaleDateString("en-PK")}</small>
                <h2>{order.items[0]?.itemName ?? "Order"}</h2>
                <p>{order.vendorName}</p>
              </div>
              <b>{formatMoney(order.total, order.currency)}</b>
              <Status label={formatOrderStatus(order.status)} />
            </article>
          ))}
        </div>
      </main>
    </>
  );
}

function AuthIcon({ name }: { name: "mail" | "lock" | "eye" | "eye-off" | "user" | "store" | "arrow" }) {
  if (name === "mail") {
    return <svg aria-hidden="true" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m4 7 8 6 8-6" /></svg>;
  }
  if (name === "lock") {
    return <svg aria-hidden="true" viewBox="0 0 24 24"><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3" /></svg>;
  }
  if (name === "eye") {
    return <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M2.5 12s3.3-5 9.5-5 9.5 5 9.5 5-3.3 5-9.5 5-9.5-5-9.5-5Z" /><circle cx="12" cy="12" r="2.2" /></svg>;
  }
  if (name === "eye-off") {
    return <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m3 3 18 18M10.6 6.9A10.8 10.8 0 0 1 12 6.8c6.2 0 9.5 5.2 9.5 5.2a17 17 0 0 1-3.1 3.4M6.2 6.7C3.8 8.1 2.5 12 2.5 12s3.3 5.2 9.5 5.2c.9 0 1.7-.1 2.4-.3" /></svg>;
  }
  if (name === "user") {
    return <svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5" /><path d="M4.5 20c.7-3.4 3.1-5.2 7.5-5.2s6.8 1.8 7.5 5.2" /></svg>;
  }
  if (name === "store") {
    return <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 10h16v10H4zM3 10l2-5h14l2 5-2 2H5l-2-2Z" /><path d="M9 20v-6h6v6M8 10v2m4-2v2m4-2v2" /></svg>;
  }
  return <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 12h15M13 6l6 6-6 6" /></svg>;
}

function AuthPage({ register = false }: { register?: boolean }) {
  const { login } = useSession();
  const [role, setRole] = useState<"Customer" | "Vendor">("Customer");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberEmail, setRememberEmail] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (register) return;
    const savedEmail = window.localStorage.getItem("sahulat-login-email");
    if (savedEmail) {
      setEmail(savedEmail);
      setRememberEmail(true);
    }
  }, [register]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (register && role === "Vendor") {
      location.assign("/vendor/register");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (rememberEmail) window.localStorage.setItem("sahulat-login-email", email.trim());
      else window.localStorage.removeItem("sahulat-login-email");
      if (register) {
        await registerCustomer({ email, password, displayName });
      }
      await login(email, password);
      go("/");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-story" aria-label="About Sahulat AI">
        <div className="auth-story-glow" aria-hidden="true" />
        <SahulatBrand className="auth-story-brand" inverse onClick={() => go("/")} />
        <div className="auth-story-copy">
          <p className="auth-story-kicker">Pakistan&apos;s AI-powered marketplace</p>
          <h1>{register ? <>Create your<br />account with <em>Sahulat</em></> : <>Welcome back<br />to <em>Sahulat</em></>}</h1>
          <p className="auth-story-lede">Shop local. Smarter. With the power of AI.</p>
          <p className="auth-story-description">Discover unique products from trusted local vendors, with an AI-powered shopping experience designed for a better, fairer marketplace.</p>
        </div>
        <div className="auth-story-art" aria-hidden="true">
          <div className="auth-story-image"><img src="/home/hero-editorial.webp" alt="" /></div>
          <div className="auth-story-cart"><span><AuthIcon name="store" /></span></div>
        </div>
        <ul className="auth-story-features">
          <li><span><FeatureIcon name="spark" /></span><div><b>AI-powered search</b><small>Find exactly what you need, faster.</small></div></li>
          <li><span><FeatureIcon name="store" /></span><div><b>Trusted local vendors</b><small>Support real businesses in your community.</small></div></li>
          <li><span><FeatureIcon name="spark" /></span><div><b>Shop smarter</b><small>Personalized discovery, just for you.</small></div></li>
        </ul>
        <div className="auth-story-signature" aria-hidden="true"><span>Support Local</span><small>A BRIGHTER TOMORROW</small></div>
      </section>

      <section className="auth-panel">
        <button className="auth-back" type="button" onClick={() => go("/")}><span aria-hidden="true">←</span> Back to shop</button>
        <form className="auth-card" onSubmit={submit}>
          <div className="auth-card-heading">
            <p className="auth-card-kicker">{register ? "JOIN SAHULAT" : "WELCOME BACK"}</p>
            <h2>{register ? "Create your account" : "Sign in"}</h2>
            <p>{register ? "Create an account to discover local products your way." : "Welcome back! Sign in to continue your shopping journey with Sahulat."}</p>
          </div>

          {register && (
            <fieldset className="auth-role-switch">
              <legend>Account type</legend>
              <button type="button" className={role === "Customer" ? "active" : ""} onClick={() => setRole("Customer")}><AuthIcon name="user" /><span>Shop as customer</span></button>
              <button type="button" className={role === "Vendor" ? "active" : ""} onClick={() => setRole("Vendor")}><AuthIcon name="store" /><span>Sell as vendor</span></button>
            </fieldset>
          )}

          {register && role === "Customer" && (
            <div className="auth-field">
              <label htmlFor="auth-name">Full name</label>
              <div className="auth-input-shell"><AuthIcon name="user" /><input id="auth-name" autoComplete="name" required value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Your full name" /></div>
            </div>
          )}
          <div className="auth-field">
            <label htmlFor="auth-email">Email</label>
            <div className="auth-input-shell"><AuthIcon name="mail" /><input id="auth-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></div>
          </div>
          <div className="auth-field">
            <label htmlFor="auth-password">Password</label>
            <div className="auth-input-shell"><AuthIcon name="lock" /><input id="auth-password" type={showPassword ? "text" : "password"} autoComplete={register ? "new-password" : "current-password"} required minLength={12} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" /><button className="auth-password-toggle" type="button" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "Hide password" : "Show password"}><AuthIcon name={showPassword ? "eye-off" : "eye"} /></button></div>
          </div>

          {!register && (
            <div className="auth-options">
              <label className="auth-check"><input type="checkbox" checked={rememberEmail} onChange={(event) => setRememberEmail(event.target.checked)} /><span>Remember me</span></label>
              <button type="button" onClick={() => setError("Password reset is not available yet. Please contact Sahulat support.")}>Forgot password?</button>
            </div>
          )}
          {error && <p className="auth-error" role="alert">{error}</p>}
          <button className="auth-submit" type="submit" disabled={busy}>{busy ? "Please wait…" : register && role === "Vendor" ? "Continue to vendor registration" : register ? "Create account" : "Sign in"}<AuthIcon name="arrow" /></button>

          <div className="auth-divider"><span /> <b>OR</b> <span /></div>
          <div className="auth-alt-actions">
            <button type="button" onClick={() => go(register ? "/login" : "/register")}><AuthIcon name="user" />{register ? "Back to sign in" : "Create account"}</button>
            <button type="button" onClick={() => location.assign("/vendor/register")}><AuthIcon name="store" />Continue as Vendor</button>
          </div>
          <p className="auth-legal">By continuing, you agree to shop responsibly with Sahulat&apos;s local marketplace.</p>
        </form>
      </section>
    </main>
  );
}

function ProfilePage() {
  const { session, loading: sessionLoading, logout } = useSession();
  const [displayName, setDisplayName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!session) return;
    getProfile()
      .then((profile) => {
        setDisplayName(profile.displayName);
        setPhone(profile.phone ?? "");
        setEmail(profile.email);
      })
      .catch((reason) => setError(errorMessage(reason)));
  }, [session]);

  if (sessionLoading) {
    return <CustomerNotice title="Loading profile" description="Checking your account…" />;
  }
  if (!session) {
    return <CustomerNotice title="Sign in to view your profile" description="Manage your details after signing in." actionLabel="Sign in" actionPath="/login" />;
  }

  async function save() {
    try {
      await updateProfile(displayName, phone || null);
      setNotice("Profile updated.");
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }

  return (
    <>
      <Nav />
      <main className="page narrow">
        <h1>Profile</h1>
        <label className="field"><span>Name</span><input value={displayName} onChange={(e) => setDisplayName(e.target.value)} /></label>
        <label className="field"><span>Email</span><input value={email} readOnly /></label>
        <label className="field"><span>Phone</span><input value={phone} onChange={(e) => setPhone(e.target.value)} /></label>
        {error && <p className="error-state" role="alert">{error}</p>}
        {notice && <p role="status">{notice}</p>}
        <button type="button" className="primary" onClick={save}>Save</button>
        <button type="button" className="danger" onClick={() => logout().then(() => go("/login"))}>Sign out</button>
      </main>
    </>
  );
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isCustomerMarketplacePath(path: string): boolean {
  if (path.startsWith("/admin") || path.startsWith("/vendor")) return false;
  return (
    path === "/" ||
    path === "/search" ||
    path === "/offers" ||
    path === "/checkout" ||
    path === "/orders" ||
    path === "/login" ||
    path === "/register" ||
    path === "/profile" ||
    path.startsWith("/product/") ||
    path.startsWith("/offers/") ||
    path.startsWith("/shop/")
  );
}

export function CustomerShop({ initialPath = "/" }: { initialPath?: string }) {
  const current = usePath(initialPath);
  const pathOnly = current.split("?")[0];

  if (pathOnly === "/") return <HomePage />;
  if (pathOnly === "/search") {
    const params = new URLSearchParams(current.split("?")[1] || "");
    return <SearchPage query={params.get("q") || ""} mode={params.get("mode") || "text"} initialCategory={params.get("category") || ""} />;
  }
  if (pathOnly.startsWith("/product/")) {
    const id = pathOnly.split("/")[2];
    if (UUID_RE.test(id)) return <ProductPage productId={id} />;
  }
  if (pathOnly.startsWith("/shop/")) {
    return <StorePage slug={pathOnly.split("/")[2]} />;
  }
  if (pathOnly === "/offers") return <OffersPage />;
  if (pathOnly.startsWith("/offers/")) {
    const id = pathOnly.split("/")[2];
    if (UUID_RE.test(id)) return <OffersPage detail offerId={id} />;
  }
  if (pathOnly === "/checkout") return <CheckoutPage />;
  if (pathOnly === "/orders") return <OrdersPage />;
  if (pathOnly === "/login") return <AuthPage />;
  if (pathOnly === "/register") return <AuthPage register />;
  if (pathOnly === "/profile") return <ProfilePage />;
  notFound();
}

export { go as customerGo };
