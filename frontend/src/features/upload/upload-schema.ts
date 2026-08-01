import { z } from "zod";

/**
 * Image constraints now live in `@/lib/image-file` because the search
 * workspace picks query images too. Re-exported here so this module keeps its
 * existing public surface for the upload feature and its tests.
 */
export {
  ACCEPTED_EXTENSIONS,
  ACCEPTED_IMAGE_TYPES,
  MAX_UPLOAD_MB,
  validateImageFile,
} from "@/lib/image-file";

/**
 * Metadata fields (the image file is handled separately in component state).
 * Optional fields are plain strings defaulting to `""` for controlled inputs;
 * empty values are omitted when the multipart body is assembled.
 */
export const uploadMetadataSchema = z.object({
  name: z.string().min(1, "Name is required").max(200, "Name is too long"),
  brand: z.string().max(100, "Brand is too long"),
  category: z.string().max(100, "Category is too long"),
  description: z.string().max(2000, "Description is too long"),
  price: z.string().refine((v) => v === "" || (!Number.isNaN(Number(v)) && Number(v) >= 0), {
    message: "Price must be a positive number",
  }),
});

export type UploadMetadata = z.infer<typeof uploadMetadataSchema>;

export const UPLOAD_DEFAULTS: UploadMetadata = {
  name: "",
  brand: "",
  category: "",
  description: "",
  price: "",
};

/** Assemble the multipart body, omitting empty optional fields. */
export function buildUploadFormData(values: UploadMetadata, file: File): FormData {
  const formData = new FormData();
  formData.append("name", values.name.trim());
  formData.append("file", file);
  if (values.brand.trim()) formData.append("brand", values.brand.trim());
  if (values.category.trim()) formData.append("category", values.category.trim());
  if (values.description.trim()) formData.append("description", values.description.trim());
  if (values.price.trim()) formData.append("price", values.price.trim());
  return formData;
}
