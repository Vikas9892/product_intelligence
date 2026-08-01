"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { FileDropzone } from "@/components/forms/file-dropzone";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ACCEPTED_EXTENSIONS, validateImageFile } from "@/lib/image-file";
import {
  buildUploadFormData,
  UPLOAD_DEFAULTS,
  uploadMetadataSchema,
  type UploadMetadata,
} from "@/features/upload/upload-schema";

/**
 * The product being checked.
 *
 * `POST /products/check-duplicate` takes exactly the upload field set, so the
 * schema and multipart builder are reused rather than restated — the two calls
 * cannot drift on validation rules or field names. Unlike upload, this endpoint
 * stores nothing.
 */
export function DuplicateForm({
  onSubmit,
  isChecking,
}: {
  onSubmit: (payload: { formData: FormData; values: UploadMetadata; file: File }) => void;
  isChecking: boolean;
}) {
  const form = useForm<UploadMetadata>({
    resolver: zodResolver(uploadMetadataSchema),
    defaultValues: UPLOAD_DEFAULTS,
  });

  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  function handleFileChange(next: File | null) {
    setFile(next);
    setFileError(next ? validateImageFile(next) : null);
  }

  function submit(values: UploadMetadata) {
    if (!file) {
      setFileError("An image is required.");
      return;
    }
    const validationError = validateImageFile(file);
    if (validationError) {
      setFileError(validationError);
      return;
    }
    onSubmit({ formData: buildUploadFormData(values, file), values, file });
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(submit)} className="grid gap-6 md:grid-cols-2">
        <FileDropzone
          value={file}
          onChange={handleFileChange}
          onValidate={validateImageFile}
          accept={ACCEPTED_EXTENSIONS}
          error={fileError}
          disabled={isChecking}
        />

        <div className="space-y-4">
          <FormField
            control={form.control}
            name="name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Name</FormLabel>
                <FormControl>
                  <Input {...field} disabled={isChecking} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <FormField
              control={form.control}
              name="brand"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Brand</FormLabel>
                  <FormControl>
                    <Input {...field} disabled={isChecking} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="category"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Category</FormLabel>
                  <FormControl>
                    <Input {...field} disabled={isChecking} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>

          <FormField
            control={form.control}
            name="price"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Price</FormLabel>
                <FormControl>
                  <Input {...field} type="number" min={0} disabled={isChecking} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="description"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Description</FormLabel>
                <FormControl>
                  <Textarea {...field} rows={3} disabled={isChecking} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <Button type="submit" disabled={isChecking} className="w-full">
            {isChecking ? "Checking…" : "Check for duplicates"}
          </Button>
        </div>
      </form>
    </Form>
  );
}
