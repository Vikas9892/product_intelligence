/**
 * The backend has no "get product" endpoint; a product's descriptive fields
 * live in the Qdrant payload returned inside a search result's `metadata`
 * (an untyped `Record<string, unknown>`). These helpers read that payload into
 * a typed shape, defensively coercing each field. Shared by the product list
 * (Milestone 3) and product detail (Milestone 4).
 */
export interface ProductMeta {
  name?: string;
  brand?: string;
  category?: string;
  price?: number;
  description?: string;
  color?: string;
  material?: string;
  gender?: string;
  season?: string;
  style?: string;
  tags: string[];
  qualityScore?: number;
}

function str(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function num(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

export function readProductMeta(metadata: Record<string, unknown> | undefined | null): ProductMeta {
  const m = metadata ?? {};
  return {
    name: str(m.name),
    brand: str(m.brand),
    category: str(m.category),
    price: num(m.price),
    description: str(m.description),
    color: str(m.color),
    material: str(m.material),
    gender: str(m.gender),
    season: str(m.season),
    style: str(m.style),
    tags: stringList(m.tags),
    qualityScore: num(m.quality_score),
  };
}
