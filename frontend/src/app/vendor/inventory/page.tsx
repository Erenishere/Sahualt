import { redirect } from "next/navigation";

export default function LegacyInventoryRedirect() {
  redirect("/vendor/catalog");
}
