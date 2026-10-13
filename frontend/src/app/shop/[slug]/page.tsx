import { CustomerShop } from "@/components/customer-shop";

type Props = { params: Promise<{ slug: string }> };

export default async function ShopPage({ params }: Props) {
  const { slug } = await params;
  return <CustomerShop initialPath={`/shop/${slug}`} />;
}
