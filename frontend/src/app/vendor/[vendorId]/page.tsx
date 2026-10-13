import { redirect } from "next/navigation";
import { legacyVendorStorefrontUrl } from "@/lib/vendor-routing";

export default async function LegacyVendorStorefront({
  params,
}: {
  params: Promise<{ vendorId: string }>;
}) {
  const { vendorId } = await params;
  redirect(legacyVendorStorefrontUrl(vendorId));
}
