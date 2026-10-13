export function legacyVendorStorefrontUrl(vendorSlug: string) {
  return `/shop/${encodeURIComponent(vendorSlug)}`;
}
