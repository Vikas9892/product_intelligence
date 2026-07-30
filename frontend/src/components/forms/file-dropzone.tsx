"use client";

import { ImageUp, X } from "lucide-react";
import Image from "next/image";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Accessible drag-and-drop image picker with preview.
 *
 * Controlled: the parent owns the `File`. Supports drag-drop, click/keyboard to
 * browse, and clearing. Client-side type/size validation is delegated to the
 * parent via `onValidate` so the rules live in one place. Purely presentational
 * beyond file selection — it does not upload.
 */
export function FileDropzone({
  value,
  onChange,
  onValidate,
  accept,
  error,
  disabled,
}: {
  value: File | null;
  onChange: (file: File | null) => void;
  onValidate?: (file: File) => string | null;
  accept?: string;
  error?: string | null;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const [isDragging, setIsDragging] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!value) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(value);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [value]);

  const accept_ = accept;

  const select = useCallback(
    (file: File | null) => {
      if (!file) {
        onChange(null);
        return;
      }
      const validationError = onValidate?.(file);
      if (validationError) {
        onChange(null);
        return;
      }
      onChange(file);
    },
    [onChange, onValidate],
  );

  function onDrop(event: React.DragEvent) {
    event.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    const file = event.dataTransfer.files?.[0] ?? null;
    select(file);
  }

  return (
    <div className="space-y-2">
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={accept_}
        className="sr-only"
        disabled={disabled}
        onChange={(e) => select(e.target.files?.[0] ?? null)}
      />

      {value && previewUrl ? (
        <div className="relative overflow-hidden rounded-xl border">
          {/* object URL of a user-selected local file; next/image optimization not applicable */}
          <Image
            src={previewUrl}
            alt={`Preview of ${value.name}`}
            width={640}
            height={360}
            unoptimized
            className="max-h-72 w-full object-contain"
          />
          <div className="bg-background/80 flex items-center justify-between gap-2 border-t px-3 py-2 text-sm backdrop-blur">
            <span className="truncate">
              {value.name} · {(value.size / 1024 / 1024).toFixed(2)} MB
            </span>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Remove image"
              onClick={() => onChange(null)}
              disabled={disabled}
            >
              <X className="size-4" />
            </Button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            if (!disabled) setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={onDrop}
          disabled={disabled}
          aria-describedby={error ? `${inputId}-error` : undefined}
          className={cn(
            "focus-visible:ring-ring flex min-h-44 w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed p-8 text-center transition-colors focus-visible:ring-2 focus-visible:outline-none disabled:opacity-50",
            isDragging ? "border-primary bg-primary/5" : "hover:bg-muted/50",
            error && "border-destructive",
          )}
        >
          <div className="bg-muted text-muted-foreground flex size-12 items-center justify-center rounded-full">
            <ImageUp className="size-6" />
          </div>
          <p className="text-sm font-medium">Drop an image here, or click to browse</p>
          <p className="text-muted-foreground text-xs">JPG, PNG, or WebP · up to 10 MB</p>
        </button>
      )}

      {error ? (
        <p id={`${inputId}-error`} className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
    </div>
  );
}
