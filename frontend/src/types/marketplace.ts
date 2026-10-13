export type PublicProductSummary = {
  productId: string;
  name: string;
  vendorId: string;
  vendorName: string;
  vendorSlug: string;
  category: string | null;
  startingPrice: number;
  currency: string;
  availability: string;
  availableStock: number | null;
  allowsOffers: boolean;
  primaryImageId: string | null;
};

export type PublicProductPage = {
  items: PublicProductSummary[];
  nextAfter: string | null;
};

export type PublicListing = {
  listingId: string;
  variantId: string;
  variantCode: string;
  sku: string | null;
  color: string | null;
  size: string | null;
  price: number;
  currency: string;
  availability: string;
  availableStock: number | null;
  allowsOffers: boolean;
};

export type PublicProductDetails = {
  productId: string;
  name: string;
  description: string;
  vendorId: string;
  vendorName: string;
  vendorSlug: string;
  vendorDescription: string | null;
  category: string | null;
  primaryImageId: string | null;
  listings: PublicListing[];
};

export type AuthSession = {
  userId: string;
  roles: string[];
  vendors: { vendorId: string; role: string }[];
};

export type AccountProfile = {
  userId: string;
  email: string;
  displayName: string;
  phone: string | null;
  addresses: CustomerAddress[];
};

export type CustomerAddress = {
  addressId: string;
  label: string;
  recipientName: string;
  phone: string;
  addressLine1: string;
  addressLine2: string | null;
  city: string;
  province: string | null;
  postalCode: string | null;
  isDefault: boolean;
};

export type OfferRecord = {
  offerId: string;
  offerNumber: string;
  listingId: string;
  productId: string;
  productName: string;
  vendorId: string;
  vendorName: string;
  listedPrice: number;
  offeredPrice: number;
  counterPrice: number | null;
  currency: string;
  status: string;
  customerMessage: string | null;
  expiresAt: string;
  createdAt: string;
  updatedAt: string;
};

export type OrderItemRecord = {
  orderItemId: string;
  listingId: string;
  productId: string;
  variantId: string;
  itemName: string;
  variantCode: string;
  sku: string | null;
  unitPrice: number;
  currency: string;
  quantity: number;
  discountTotal: number;
  lineTotal: number;
};

export type DeliveryDetails = {
  name: string;
  phone: string;
  addressLine1: string;
  addressLine2: string | null;
  city: string;
  province: string | null;
  postalCode: string | null;
};

export type OrderRecord = {
  orderId: string;
  orderNumber: string;
  customerUserId: string;
  vendorId: string;
  vendorName: string;
  status: string;
  paymentMethod: string;
  paymentStatus: string;
  currency: string;
  subtotal: number;
  discountTotal: number;
  deliveryTotal: number;
  total: number;
  delivery: DeliveryDetails;
  placedAt: string;
  updatedAt: string;
  items: OrderItemRecord[];
};

export type CheckoutDraft = {
  listingId: string;
  productId: string;
  productName: string;
  vendorName: string;
  unitPrice: number;
  currency: string;
  quantity: number;
  imageUrl?: string;
  acceptedOfferId?: string;
};
