import type {
  AccountProfile,
  AuthSession,
  CheckoutDraft,
  OfferRecord,
  OrderRecord,
  PublicProductDetails,
  PublicProductPage,
  PublicProductSummary,
} from "@/types/marketplace";
import {
  backendAssetUrl,
  backendGet,
  backendPost,
  backendPostForm,
  backendPut,
  BackendRequestError,
} from "@/services/backend-client";

export function catalogImageUrl(productId: string, imageId: string): string {
  return backendAssetUrl(`/api/v1/catalog/products/${productId}/images/${imageId}`);
}

export function productImageUrl(product: { productId: string; primaryImageId: string | null }): string {
  return product.primaryImageId
    ? catalogImageUrl(product.productId, product.primaryImageId)
    : "/products/midnight-kurta.webp";
}

export type CatalogSearchPage = {
  mode: string;
  query: string | null;
  items: PublicProductSummary[];
  nextAfter: string | null;
};

export async function searchCatalog(params: {
  query?: string;
  category?: string;
  vendor?: string;
  after?: string;
  limit?: number;
  mode?: string;
}): Promise<PublicProductPage | CatalogSearchPage> {
  const mode = params.mode ?? "text";
  if (mode !== "text" && mode !== "keyword") {
    const search = new URLSearchParams();
    if (params.query) search.set("q", params.query);
    search.set("mode", mode);
    if (params.category) search.set("category", params.category);
    if (params.vendor) search.set("vendor", params.vendor);
    search.set("limit", String(params.limit ?? 24));
    return backendGet<CatalogSearchPage>(`/api/v1/catalog/search?${search}`);
  }
  const search = new URLSearchParams();
  if (params.query) search.set("query", params.query);
  if (params.category) search.set("category", params.category);
  if (params.vendor) search.set("vendor", params.vendor);
  if (params.after) search.set("after", params.after);
  search.set("limit", String(params.limit ?? 24));
  return backendGet<PublicProductPage>(`/api/v1/catalog/products?${search}`);
}

export async function searchCatalogImage(file: File, limit = 24): Promise<CatalogSearchPage> {
  const form = new FormData();
  form.append("image", file);
  return backendPostForm<CatalogSearchPage>(`/api/v1/catalog/search/image?limit=${limit}`, form);
}

export async function searchCatalogVoice(file: File, language = "en", limit = 24): Promise<CatalogSearchPage> {
  const form = new FormData();
  form.append("audio", file);
  return backendPostForm<CatalogSearchPage>(
    `/api/v1/catalog/search/voice?language=${language}&limit=${limit}`,
    form,
  );
}

export async function getProduct(productId: string): Promise<PublicProductDetails | null> {
  try {
    return await backendGet<PublicProductDetails>(`/api/v1/catalog/products/${productId}`);
  } catch (error) {
    if (error instanceof BackendRequestError && error.status === 404) return null;
    throw error;
  }
}

export async function fetchSession(): Promise<AuthSession | null> {
  try {
    return await backendGet<AuthSession>("/api/v1/auth/me");
  } catch (error) {
    if (error instanceof BackendRequestError && error.status === 401) return null;
    throw error;
  }
}

export async function login(email: string, password: string): Promise<void> {
  await backendPost("/api/v1/auth/login", { email, password });
}

export async function logout(): Promise<void> {
  await backendPost("/api/v1/auth/logout");
}

export async function registerCustomer(body: {
  email: string;
  password: string;
  displayName: string;
  phone?: string;
}): Promise<void> {
  await backendPost("/api/v1/auth/customer-registrations", body);
}

export async function getProfile(): Promise<AccountProfile> {
  return backendGet<AccountProfile>("/api/v1/account/profile");
}

export async function updateProfile(displayName: string, phone: string | null): Promise<void> {
  await backendPut("/api/v1/account/profile", { displayName, phone });
}

export async function listOffers(status?: string): Promise<OfferRecord[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return backendGet<OfferRecord[]>(`/api/v1/offers${query}`);
}

export async function getOffer(offerId: string): Promise<OfferRecord | null> {
  try {
    return await backendGet<OfferRecord>(`/api/v1/offers/${offerId}`);
  } catch (error) {
    if (error instanceof BackendRequestError && error.status === 404) return null;
    throw error;
  }
}

export async function createOffer(listingId: string, offeredPrice: number, message?: string): Promise<OfferRecord> {
  return backendPost<OfferRecord>("/api/v1/offers", {
    listingId,
    offeredPrice,
    message: message?.trim() || undefined,
  });
}

export async function withdrawOffer(offerId: string): Promise<void> {
  await backendPost(`/api/v1/offers/${offerId}/withdraw`);
}

export async function acceptCounterOffer(offerId: string): Promise<void> {
  await backendPost(`/api/v1/offers/${offerId}/accept-counter`);
}

export async function listOrders(status?: string): Promise<OrderRecord[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return backendGet<OrderRecord[]>(`/api/v1/orders${query}`);
}

export async function placeOrder(
  draft: CheckoutDraft,
  delivery: {
    name: string;
    phone: string;
    addressLine1: string;
    addressLine2?: string;
    city: string;
    province?: string;
    postalCode?: string;
  },
  idempotencyKey: string,
): Promise<OrderRecord> {
  return backendPost<OrderRecord>("/api/v1/orders", {
    idempotencyKey,
    items: [{ listingId: draft.listingId, quantity: draft.quantity }],
    acceptedOfferId: draft.acceptedOfferId ?? null,
    paymentMethod: "cash_on_delivery",
    delivery: {
      name: delivery.name,
      phone: delivery.phone,
      addressLine1: delivery.addressLine1,
      addressLine2: delivery.addressLine2 ?? null,
      city: delivery.city,
      province: delivery.province ?? null,
      postalCode: delivery.postalCode ?? null,
    },
  });
}

export const CHECKOUT_STORAGE_KEY = "sahulat-checkout-draft";
export const CHECKOUT_IDEMPOTENCY_KEY = "sahulat-checkout-idempotency";

export function readCheckoutDraft(): CheckoutDraft | null {
  try {
    return JSON.parse(sessionStorage.getItem(CHECKOUT_STORAGE_KEY) || "null") as CheckoutDraft | null;
  } catch {
    return null;
  }
}

export function saveCheckoutDraft(draft: CheckoutDraft): void {
  sessionStorage.setItem(CHECKOUT_STORAGE_KEY, JSON.stringify(draft));
}

export function clearCheckoutDraft(): void {
  sessionStorage.removeItem(CHECKOUT_STORAGE_KEY);
  sessionStorage.removeItem(CHECKOUT_IDEMPOTENCY_KEY);
}

export function formatMoney(amount: number, currency = "PKR"): string {
  return `${currency} ${amount.toLocaleString("en-PK")}`;
}

export function formatOfferStatus(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function formatOrderStatus(status: string): string {
  const map: Record<string, string> = {
    placed: "Placed",
    confirmed: "Confirmed",
    processing: "Processing",
    shipped: "Shipped",
    completed: "Completed",
    cancelled: "Cancelled",
  };
  return map[status] ?? status;
}
