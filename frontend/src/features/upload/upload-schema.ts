import { z } from "zod";

/** Client-side mirrors of the backend's upload constraints (fail fast; the
 * server remains the source of truth). See backend `STORAGE__*` settings. */
export const MAX_UPLOAD_MB = 10;
export const ACCEPTED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;
export const ACCEPTED_EXTENSIONS = ".jpg,.jpeg,.png,.webp";

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

/** Validate a chosen file against type/size; returns an error message or null. */
export function validateImageFile(file: File): string | null {
  if (!ACCEPTED_IMAGE_TYPES.includes(file.type as (typeof ACCEPTED_IMAGE_TYPES)[number])) {
    return "Unsupported file type. Use JPG, PNG, or WebP.";
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `File is too large (max ${MAX_UPLOAD_MB} MB).`;
  }
  return null;
}

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
