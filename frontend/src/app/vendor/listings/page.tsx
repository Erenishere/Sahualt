import { redirect } from "next/navigation";

export default function LegacyListingsRedirect() {
  redirect("/vendor/catalog");
}
