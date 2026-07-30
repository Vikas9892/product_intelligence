"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { FileDropzone } from "@/components/forms/file-dropzone";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

import {
  ACCEPTED_EXTENSIONS,
  buildUploadFormData,
  UPLOAD_DEFAULTS,
  uploadMetadataSchema,
  validateImageFile,
  type UploadMetadata,
} from "./upload-schema";

/**
 * Product metadata form + image dropzone. Validates with Zod (mirroring the
 * backend constraints), requires an image, and hands a ready multipart body to
 * the parent on submit. It performs no network calls itself.
 */
export function UploadForm({
  onSubmit,
  isSubmitting,
}: {
  onSubmit: (formData: FormData) => void;
  isSubmitting: boolean;
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
    onSubmit(buildUploadFormData(values, file));
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(submit)} className="grid gap-6 md:grid-cols-2">
        <div className="space-y-2">
          <FileDropzone
            value={file}
            onChange={handleFileChange}
            onValidate={validateImageFile}
            accept={ACCEPTED_EXTENSIONS}
            error={fileError}
            disabled={isSubmitting}
          />
        </div>

        <div className="space-y-4">
          <FormField
            control={form.control}
            name="name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Name</FormLabel>
                <FormControl>
                  <Input placeholder="Blue Running Shoes" {...field} disabled={isSubmitting} />
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
                    <Input placeholder="Nike" {...field} disabled={isSubmitting} />
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
                    <Input placeholder="Men Shoes" {...field} disabled={isSubmitting} />
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
                  <Input
                    type="number"
                    min={0}
                    step="0.01"
                    inputMode="decimal"
                    placeholder="1999"
                    {...field}
                    disabled={isSubmitting}
                  />
                </FormControl>
                <FormDescription>Optional. No currency assumed.</FormDescription>
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
                  <Textarea
                    rows={3}
                    placeholder="Lightweight everyday running shoes…"
                    {...field}
                    disabled={isSubmitting}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <Button type="submit" disabled={isSubmitting} className="w-full sm:w-auto">
            {isSubmitting ? "Uploading…" : "Upload product"}
          </Button>
        </div>
      </form>
    </Form>
  );
}
