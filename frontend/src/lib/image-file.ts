/**
 * Shared client-side image-file constraints.
 *
 * These mirror the backend's `STORAGE__*` settings (`MAX_UPLOAD_SIZE_MB`,
 * `ALLOWED_IMAGE_EXTENSIONS`) so the UI can fail fast; the server remains the
 * source of truth and its `422` is still handled.
 *
 * Lives in `lib/` rather than inside a feature because two features now pick
 * images: upload (a product image to index) and search (a query image). One
 * definition, so the two can never diverge on what "a valid image" means.
 */
export const MAX_UPLOAD_MB = 10;
export const ACCEPTED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;
export const ACCEPTED_EXTENSIONS = ".jpg,.jpeg,.png,.webp";

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
