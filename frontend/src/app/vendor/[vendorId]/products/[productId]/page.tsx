"use client";

import Link from "next/link";
import Image from "next/image";
import { useParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { backendAssetUrl, backendGet, backendPost, backendPostForm, backendPut, BackendRequestError } from "@/services/backend-client";
import { VendorHeader } from "@/components/vendor-header";
import styles from "./product-detail.module.css";

type Listing = {
  listingId: string;
  listingStatus: string;
  price: number | null;
  currency: string | null;
  availability: string;
  onHandQuantity: number | null;
  reservedQuantity: number;
};

type Product = {
  productId: string;
  productName: string;
  description: string;
  productStatus: string;
  listings: Listing[];
  hasMoreListings: boolean;
  categoryId: string | null;
  images: { imageId: string; mimeType: string; width: number | null; height: number | null; isPrimary: boolean }[] | null;
};
type Session = { vendors: { vendorId: string; role: string }[] };
type Category = { categoryId: string; name: string; parentId: string | null };
type Publication = {
  hasCategory: boolean;
  hasActiveImage: boolean;
  hasActiveDefaultVariant: boolean;
  hasCompleteListing: boolean;
};

function errorMessage(error: unknown): string {
  return error instanceof BackendRequestError ? error.message : "Catalog is unavailable. Please try again.";
}

function availableStock(listing: Listing): string {
  return listing.onHandQuantity === null
    ? "Unknown"
    : String(listing.onHandQuantity - listing.reservedQuantity);
}

function StockEditor({ vendorId, productId, listing, onSaved }: {
  vendorId: string;
  productId: string;
  listing: Listing;
  onSaved: () => Promise<void>;
}) {
  const [unknown, setUnknown] = useState(listing.onHandQuantity === null);
  const [quantity, setQuantity] = useState(listing.onHandQuantity === null ? "" : String(listing.onHandQuantity));
  const [availability, setAvailability] = useState(listing.availability === "unknown" ? "unavailable" : listing.availability);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setUnknown(listing.onHandQuantity === null);
    setQuantity(listing.onHandQuantity === null ? "" : String(listing.onHandQuantity));
    setAvailability(listing.availability === "unknown" ? "unavailable" : listing.availability);
  }, [listing.onHandQuantity, listing.availability]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    const amount = Number(quantity);
    if (!unknown && (!Number.isInteger(amount) || amount < listing.reservedQuantity || amount > 1_000_000)) {
      setError(`Enter a whole quantity from ${listing.reservedQuantity} to 1,000,000, or mark stock unknown.`);
      return;
    }
    if (!unknown && amount === 0 && availability === "in_stock") {
      setError("Zero stock cannot be marked in stock.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await backendPut(
        `/api/v1/vendors/${encodeURIComponent(vendorId)}/catalog/products/${encodeURIComponent(productId)}/listings/${encodeURIComponent(listing.listingId)}/stock`,
        { onHandQuantity: unknown ? null : amount, availability },
      );
      await onSaved();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSaving(false);
    }
  }

  return <form className={styles.stockForm} onSubmit={save}>
    <strong>Listing <code>{listing.listingId}</code></strong>
    <p>Reserved: {listing.reservedQuantity}. Stock cannot be set below reservations.</p>
    <div className={styles.formGrid}>
      <label>On-hand quantity
        <input type="number" min={listing.reservedQuantity} max={1000000} step="1" required={!unknown}
          disabled={unknown} value={quantity} onChange={(event) => setQuantity(event.target.value)} />
      </label>
      <label>Availability
        <select value={availability} onChange={(event) => setAvailability(event.target.value)}>
          <option value="in_stock">In stock</option>
          <option value="out_of_stock">Out of stock</option>
          <option value="preorder">Preorder</option>
          <option value="unavailable">Unavailable</option>
        </select>
      </label>
    </div>
    <label className={styles.stockUnknown}>
      <input type="checkbox" checked={unknown} onChange={(event) => setUnknown(event.target.checked)} />
      Stock quantity is unknown
    </label>
    <button type="submit" disabled={saving}>{saving ? "Saving…" : "Save stock"}</button>
    {error && <p className={styles.error} role="alert">{error}</p>}
  </form>;
}

export default function VendorProductPage() {
  const params = useParams<{ vendorId: string; productId: string }>();
  const vendorId = params.vendorId;
  const productId = params.productId;
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [canEdit, setCanEdit] = useState(false);
  const [canPublish, setCanPublish] = useState(false);
  const [publication, setPublication] = useState<Publication | null>(null);
  const [publicationError, setPublicationError] = useState("");
  const [publishing, setPublishing] = useState(false);
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryId, setCategoryId] = useState("");
  const [savingCategory, setSavingCategory] = useState(false);
  const [categoryError, setCategoryError] = useState("");
  const [variantCode, setVariantCode] = useState("");
  const [price, setPrice] = useState("");
  const [currency, setCurrency] = useState("PKR");
  const [availability, setAvailability] = useState("in_stock");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [imageError, setImageError] = useState("");

  useEffect(() => {
    let active = true;
    setCanEdit(false);
    setCanPublish(false);
    backendGet<Session>("/api/v1/auth/me")
      .then((session) => {
        if (!active) return;
        const role = session.vendors.find((vendor) => vendor.vendorId === vendorId)?.role;
        setCanEdit(role === "owner" || role === "manager" || role === "staff");
        setCanPublish(role === "owner" || role === "manager");
      })
      .catch(() => { if (active) { setCanEdit(false); setCanPublish(false); } });
    backendGet<Product>(`/api/v1/vendors/${encodeURIComponent(vendorId)}/catalog/products/${encodeURIComponent(productId)}`)
      .then((result) => {
        if (!active) return;
        setProduct(result);
        setCategoryId(result.categoryId ?? "");
      })
      .catch((reason: unknown) => {
        if (!active) return;
        if (reason instanceof BackendRequestError) {
          setError(reason.status === 401 ? "Sign in to view this product." : reason.message);
        } else {
          setError("Product details are unavailable. Please try again.");
        }
      })
      .finally(() => { if (active) setLoading(false); });
    backendGet<Category[]>(`/api/v1/vendors/${encodeURIComponent(vendorId)}/catalog/categories`)
      .then((result) => { if (active) setCategories(result); })
      .catch((reason: unknown) => { if (active) setCategoryError(errorMessage(reason)); });
    backendGet<Publication>(`/api/v1/vendors/${encodeURIComponent(vendorId)}/catalog/products/${encodeURIComponent(productId)}/publication`)
      .then((result) => { if (active) setPublication(result); })
      .catch((reason: unknown) => { if (active) setPublicationError(errorMessage(reason)); });
    return () => { active = false; };
  }, [vendorId, productId]);

  async function refreshProduct() {
    const base = `/api/v1/vendors/${encodeURIComponent(vendorId)}/catalog/products/${encodeURIComponent(productId)}`;
    const [updated, facts] = await Promise.all([
      backendGet<Product>(base), backendGet<Publication>(`${base}/publication`),
    ]);
    setProduct(updated);
    setPublication(facts);
  }

  async function saveCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!categoryId || savingCategory) return;
    setSavingCategory(true);
    setCategoryError("");
    try {
      await backendPut(
        `/api/v1/vendors/${encodeURIComponent(vendorId)}/catalog/products/${encodeURIComponent(productId)}/category`,
        { categoryId },
      );
      await refreshProduct();
    } catch (reason) {
      setCategoryError(errorMessage(reason));
    } finally {
      setSavingCategory(false);
    }
  }

  async function createVariant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const amount = Number(price);
    if (saving || !variantCode.trim() || !Number.isFinite(amount) || amount <= 0) return;
    setSaving(true);
    setSaveError("");
    try {
      await backendPost(
        `/api/v1/vendors/${encodeURIComponent(vendorId)}/catalog/products/${encodeURIComponent(productId)}/variants`,
        { variantCode: variantCode.trim(), price: amount, currency, availability },
      );
      await refreshProduct();
      setVariantCode("");
      setPrice("");
    } catch (reason) {
      setSaveError(errorMessage(reason));
    } finally {
      setSaving(false);
    }
  }

  async function uploadImage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!imageFile || uploadingImage) return;
    if (imageFile.size > 5 * 1024 * 1024) {
      setImageError("Choose a JPEG or PNG image no larger than 5 MB.");
      return;
    }
    setUploadingImage(true);
    setImageError("");
    try {
      const form = new FormData();
      form.append("image", imageFile);
      await backendPostForm(
        `/api/v1/vendors/${encodeURIComponent(vendorId)}/catalog/products/${encodeURIComponent(productId)}/images`,
        form,
      );
      await refreshProduct();
      setImageFile(null);
    } catch (reason) {
      setImageError(errorMessage(reason));
    } finally {
      setUploadingImage(false);
    }
  }

  async function publishProduct() {
    if (publishing || !canPublish) return;
    setPublishing(true);
    setPublicationError("");
    try {
      await backendPost(
        `/api/v1/vendors/${encodeURIComponent(vendorId)}/catalog/products/${encodeURIComponent(productId)}/publish`,
      );
      await refreshProduct();
    } catch (reason) {
      setPublicationError(errorMessage(reason));
    } finally {
      setPublishing(false);
    }
  }

  return <main className={styles.page}>
    <VendorHeader />
    <section className={styles.panel}>
      <Link className={styles.back} href="/vendor/catalog">← Back to catalog</Link>
      {loading ? <p role="status">Loading product details…</p> : error ? (
        <div role="alert" className={styles.error}>
          <p>{error}</p>
          <Link href="/vendor/catalog">Back to catalog</Link>
        </div>
      ) : product ? <>
        <p className={styles.eyebrow}>Authorized vendor catalog</p>
        <h1>{product.productName}</h1>
        <p className={styles.status}>Product status: <strong>{product.productStatus}</strong></p>
        <p>{product.description}</p>
        {canEdit && product.productStatus === "draft" && <form className={styles.editForm} onSubmit={saveCategory}>
          <h2>Category</h2>
          <p>Select an active category for this product.</p>
          {categories.length === 0 ? <p>No active categories are available.</p> : <>
            <label>Product category
              <select value={categoryId} onChange={(event) => setCategoryId(event.target.value)} required>
                <option value="">Select a category</option>
                {categories.map((category) => <option key={category.categoryId} value={category.categoryId}>
                  {category.parentId ? "↳ " : ""}{category.name}
                </option>)}
              </select>
            </label>
            <button type="submit" disabled={savingCategory || !categoryId}>
              {savingCategory ? "Saving…" : "Save category"}
            </button>
          </>}
          {categoryError && <p className={styles.error} role="alert">{categoryError}</p>}
        </form>}
        {canEdit && product.productStatus === "draft" && <form className={styles.editForm} onSubmit={createVariant}>
          <h2>Add a variant and draft listing</h2>
          <p>Set the sellable option and its proposed price. The listing stays a draft until publication is available.</p>
          <div className={styles.formGrid}>
            <label>Variant code
              <input value={variantCode} onChange={(event) => setVariantCode(event.target.value)} maxLength={80} required placeholder="e.g. black-medium" />
            </label>
            <label>Price
              <input type="number" min="0.01" max="9999999999.99" step="0.01" value={price} onChange={(event) => setPrice(event.target.value)} required />
            </label>
            <label>Currency
              <input value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase())} maxLength={3} pattern="[A-Z]{3}" required />
            </label>
            <label>Availability
              <select value={availability} onChange={(event) => setAvailability(event.target.value)}>
                <option value="in_stock">In stock</option>
                <option value="out_of_stock">Out of stock</option>
                <option value="preorder">Preorder</option>
                <option value="unavailable">Unavailable</option>
              </select>
            </label>
          </div>
          <button type="submit" disabled={saving || !variantCode.trim() || !price}>{saving ? "Saving…" : "Add draft listing"}</button>
          {saveError && <p className={styles.error} role="alert">{saveError}</p>}
        </form>}
        {canEdit && product.productStatus === "draft" && <form className={styles.editForm} onSubmit={uploadImage}>
          <h2>Product image</h2>
          <p>Upload a JPEG or PNG image up to 5 MB. Images are stored in private catalog storage.</p>
          <label>Choose image
            <input type="file" accept="image/jpeg,image/png" onChange={(event) => setImageFile(event.target.files?.[0] ?? null)} required />
          </label>
          <button type="submit" disabled={uploadingImage || !imageFile}>
            {uploadingImage ? "Uploading…" : "Upload image"}
          </button>
          {imageError && <p className={styles.error} role="alert">{imageError}</p>}
        </form>}
        {(product.images?.length ?? 0) > 0 && <section className={styles.images} aria-label="Product images">
          {product.images?.map((image) => <Image
            key={image.imageId}
            unoptimized
            src={backendAssetUrl(`/api/v1/vendors/${encodeURIComponent(vendorId)}/catalog/products/${encodeURIComponent(productId)}/images/${encodeURIComponent(image.imageId)}`)}
            alt={product.productName}
            width={image.width ?? 320}
            height={image.height ?? 240}
          />)}
        </section>}
        <section className={styles.publication} aria-label="Publication requirements">
          <h2>Publication checklist</h2>
          {publication ? <ul>
            <li>{publication.hasCategory ? "✓" : "○"} Active category</li>
            <li>{publication.hasActiveImage ? "✓" : "○"} Product image</li>
            <li>{publication.hasActiveDefaultVariant ? "✓" : "○"} Active default variant</li>
            <li>{publication.hasCompleteListing ? "✓" : "○"} Listing with price, currency, and availability</li>
          </ul> : <p>Checking publication requirements…</p>}
          {canPublish && product.productStatus === "draft" && <button
            type="button"
            disabled={publishing || !publication || !publication.hasCategory || !publication.hasActiveImage ||
              !publication.hasActiveDefaultVariant || !publication.hasCompleteListing}
            onClick={publishProduct}
          >{publishing ? "Publishing…" : "Publish product"}</button>}
          {publicationError && <p className={styles.error} role="alert">{publicationError}</p>}
        </section>
        <h2>Listings</h2>
        {product.listings.length === 0 ? <p>No current listings for this product.</p> : <>
          <div className={styles.tableWrap}><table>
            <thead><tr><th>Listing</th><th>Status</th><th>Price</th><th>Availability</th><th>Available stock</th></tr></thead>
            <tbody>{product.listings.map((listing) => <tr key={listing.listingId}>
              <td><code>{listing.listingId}</code></td>
              <td>{listing.listingStatus}</td>
              <td>{listing.price === null || listing.currency === null ? "Unknown" : `${listing.currency} ${listing.price.toLocaleString()}`}</td>
              <td>{listing.availability}</td>
              <td>{availableStock(listing)}</td>
            </tr>)}</tbody>
          </table></div>
          {product.hasMoreListings && <p>Showing the first 50 listings.</p>}
          {canEdit && <section className={styles.stockEditors} aria-label="Update listing stock">
            <h2>Update stock and availability</h2>
            {product.listings.map((listing) => <StockEditor key={listing.listingId}
              vendorId={vendorId} productId={productId} listing={listing} onSaved={refreshProduct} />)}
          </section>}
        </>}
        <p className={styles.note}>Stock marked unknown has not been reported; it is not zero.</p>
      </> : null}
    </section>
  </main>;
}
