import { Upload } from "lucide-react";

import { PageHeader } from "@/components/common/page-header";
import { PagePlaceholder } from "@/components/common/page-placeholder";

export default function UploadPage() {
  return (
    <>
      <PageHeader title="Upload" description="Add a product image and metadata to the catalog." />
      <PagePlaceholder icon={Upload} stage="Stage 4" />
    </>
  );
}
