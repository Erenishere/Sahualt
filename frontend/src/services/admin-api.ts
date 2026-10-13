import { backendGet, backendPut, BackendRequestError } from "@/services/backend-client";

export type AdminSummary = {
  registeredVendors: number;
  activeListings: number;
  registeredUsers: number;
  pendingVendors: number;
  recentActivity: {
    activityId: string;
    entityType: string;
    entityId: string;
    action: string;
    vendorId: string | null;
    createdAt: string;
  }[];
};

export type AdminUser = {
  userId: string;
  email: string;
  displayName: string;
  status: string;
  createdAt: string;
  roles: string[];
};

export type AdminVendor = {
  vendorId: string;
  displayName: string;
  slug: string;
  status: string;
  createdAt: string;
  activeMembers: number;
  productCount: number;
};

export async function adminSummary(): Promise<AdminSummary> {
  return backendGet("/api/v1/admin/summary");
}

export async function adminUsers(status?: string): Promise<AdminUser[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return backendGet(`/api/v1/admin/users${q}`);
}

export async function adminVendors(status?: string): Promise<AdminVendor[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return backendGet(`/api/v1/admin/vendors${q}`);
}

export async function setUserStatus(userId: string, status: string): Promise<void> {
  await backendPut(`/api/v1/admin/users/${userId}/status`, { status });
}

export async function setVendorStatus(vendorId: string, status: string): Promise<void> {
  await backendPut(`/api/v1/admin/vendors/${vendorId}/status`, { status });
}

export function adminError(error: unknown): string {
  return error instanceof BackendRequestError ? error.message : "Request failed.";
}
