import { backendGet, backendPut, BackendRequestError } from "@/services/backend-client";
import type { OfferRecord, OrderRecord } from "@/types/marketplace";

export type VendorCommerceSummary = {
  pendingOffers: number;
  openOrders: number;
  lowStockListings: number;
  unknownStockListings: number;
};

export type VendorAnalytics = {
  periodDays: number;
  ordersPlaced: number;
  ordersCompleted: number;
  revenue: { currency: string; amount: number }[];
  averageOrderValue: { currency: string; amount: number }[];
  offersReceived: number;
  offersAccepted: number;
  offersConverted: number;
  topProducts: {
    productId: string;
    name: string;
    currency: string;
    quantity: number;
    revenue: number;
  }[];
};

export type VendorStoreProfile = {
  vendorId: string;
  displayName: string;
  slug: string;
  description: string | null;
  allowCustomerOffers: boolean;
};

export async function vendorSummary(vendorId: string): Promise<VendorCommerceSummary> {
  return backendGet(`/api/v1/vendors/${vendorId}/commerce/summary`);
}

export async function vendorAnalytics(vendorId: string, periodDays = 30): Promise<VendorAnalytics> {
  return backendGet(`/api/v1/vendors/${vendorId}/commerce/analytics?periodDays=${periodDays}`);
}

export async function vendorOffers(vendorId: string, status?: string): Promise<OfferRecord[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return backendGet(`/api/v1/vendors/${vendorId}/commerce/offers${q}`);
}

export async function vendorDecideOffer(
  vendorId: string,
  offerId: string,
  action: "accept" | "counter" | "reject",
  counterPrice?: number,
): Promise<void> {
  await backendPut(`/api/v1/vendors/${vendorId}/commerce/offers/${offerId}/decision`, {
    action,
    counterPrice: counterPrice ?? null,
  });
}

export async function vendorOrders(vendorId: string, status?: string): Promise<OrderRecord[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return backendGet(`/api/v1/vendors/${vendorId}/commerce/orders${q}`);
}

export async function vendorTransitionOrder(
  vendorId: string,
  orderId: string,
  status: string,
): Promise<void> {
  await backendPut(`/api/v1/vendors/${vendorId}/commerce/orders/${orderId}/status`, { status });
}

export async function vendorSettings(vendorId: string): Promise<VendorStoreProfile> {
  return backendGet(`/api/v1/vendors/${vendorId}/settings`);
}

export async function updateVendorSettings(
  vendorId: string,
  body: { displayName: string; description?: string | null; allowCustomerOffers: boolean },
): Promise<void> {
  await backendPut(`/api/v1/vendors/${vendorId}/settings`, body);
}

export function vendorError(error: unknown): string {
  return error instanceof BackendRequestError ? error.message : "Request failed.";
}
