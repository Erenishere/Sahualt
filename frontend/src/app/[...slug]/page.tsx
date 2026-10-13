import { CustomerShop } from "@/components/customer-shop";
import { notFound } from "next/navigation";

const routes = new Set([
  "search",
  "offers",
  "checkout",
  "orders",
  "login",
  "register",
  "profile",
]);
const uuid = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const productRoute = new RegExp(`^product/${uuid}$`, "i");
const offerRoute = new RegExp(`^offers/${uuid}$`, "i");

type RouteProps = {
  params: Promise<{ slug: string[] }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function CustomerCatchAll({ params, searchParams }: RouteProps) {
  const { slug } = await params;
  const path = slug.join("/");
  const isSupported =
    routes.has(path) ||
    productRoute.test(path) ||
    offerRoute.test(path);
  if (!isSupported) notFound();

  const query = new URLSearchParams();
  if (path === "search") {
    const search = await searchParams;
    for (const key of ["q", "mode"]) {
      const value = search?.[key];
      if (typeof value === "string") query.set(key, value);
    }
  }

  return <CustomerShop initialPath={`/${path}${query.size ? `?${query}` : ""}`} />;
}
