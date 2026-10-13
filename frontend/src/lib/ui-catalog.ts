export type ProductRecord = {
  id: number;
  name: string;
  vendor: string;
  price: number;
  category: string;
  color: string;
  stock: number | null;
  image: string;
  sizes: string[];
  listingStatus: "active" | "draft";
};

export const products: ProductRecord[] = [
  { id: 1, name: "Midnight Embroidered Kurta", vendor: "Mehr Studio", price: 4500, category: "Ready to Wear", color: "Black", stock: 4, image: "/products/midnight-kurta.svg", sizes: ["S", "M", "L"], listingStatus: "active" },
  { id: 2, name: "Classic Black Cotton Kurta", vendor: "Noor Collective", price: 3900, category: "Kurtas", color: "Jet Black", stock: 12, image: "/products/classic-kurta.svg", sizes: ["M", "L", "XL"], listingStatus: "active" },
  { id: 3, name: "Onyx Formal Kurta", vendor: "Zarq Boutique", price: 5200, category: "Formal", color: "Onyx", stock: 2, image: "/products/onyx-kurta.svg", sizes: ["S", "M", "L"], listingStatus: "active" },
  { id: 4, name: "Sapphire Floral Three-Piece", vendor: "Riwaayat", price: 6850, category: "Lawn", color: "Sapphire", stock: 7, image: "/products/classic-kurta.svg", sizes: ["S", "M", "L"], listingStatus: "active" },
  { id: 5, name: "Ivory Embroidered Ensemble", vendor: "Nazaakat Studio", price: 7900, category: "Formal", color: "Ivory", stock: null, image: "/products/onyx-kurta.svg", sizes: ["M", "L"], listingStatus: "active" },
  { id: 6, name: "Indigo Summer Lawn Suit", vendor: "Mehr Studio", price: 4250, category: "Unstitched", color: "Indigo", stock: 15, image: "/products/midnight-kurta.svg", sizes: ["S", "M", "L", "XL"], listingStatus: "draft" },
  { id: 7, name: "Rosewater Embroidered Suit", vendor: "Mehr Studio", price: 6100, category: "Formal", color: "Rosewater", stock: null, image: "/products/onyx-kurta.svg", sizes: ["M", "L"], listingStatus: "active" },
];


