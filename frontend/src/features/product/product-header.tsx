import { PageHeader } from "@/components/common/page-header";
import { Badge } from "@/components/ui/badge";
import type { ProductMeta } from "@/lib/api/product-metadata";
import { formatPrice } from "@/lib/format";

export function ProductHeader({ id, meta }: { id: string; meta: ProductMeta | null }) {
  const title = meta?.name ?? `Product ${id.slice(0, 8)}`;

  return (
    <PageHeader
      title={title}
      description={`ID ${id}`}
      actions={
        <div className="flex flex-wrap gap-2">
          {meta?.brand ? <Badge variant="secondary">{meta.brand}</Badge> : null}
          {meta?.category ? <Badge variant="outline">{meta.category}</Badge> : null}
          {meta?.price !== undefined ? (
            <Badge className="tabular-nums">{formatPrice(meta.price)}</Badge>
          ) : null}
        </div>
      }
    />
  );
}
