import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { JobProgress } from "@/features/upload/job-progress";
import { isTerminal } from "@/features/upload/queries";
import {
  buildUploadFormData,
  UPLOAD_DEFAULTS,
  validateImageFile,
} from "@/features/upload/upload-schema";
import type { JobStatusResponse } from "@/lib/api/types";

function jpeg(sizeBytes = 1000): File {
  const file = new File([new Uint8Array(sizeBytes)], "shoe.jpg", { type: "image/jpeg" });
  Object.defineProperty(file, "size", { value: sizeBytes });
  return file;
}

const JOB: JobStatusResponse = {
  job_id: "job-1",
  product_id: "prod-1",
  status: "running",
  progress: 40,
  current_stage: "Processing Upload",
  retry_count: 0,
  max_retries: 5,
  error: null,
  created_at: "2026-07-24T10:00:00Z",
  updated_at: "2026-07-24T10:00:01Z",
};

describe("upload validation", () => {
  it("rejects non-image types", () => {
    const pdf = new File(["x"], "f.pdf", { type: "application/pdf" });
    expect(validateImageFile(pdf)).toMatch(/Unsupported/);
  });

  it("rejects oversized images", () => {
    expect(validateImageFile(jpeg(11 * 1024 * 1024))).toMatch(/too large/);
  });

  it("accepts a valid image", () => {
    expect(validateImageFile(jpeg())).toBeNull();
  });
});

describe("buildUploadFormData", () => {
  it("includes name and file, omits empty optionals", () => {
    const fd = buildUploadFormData({ ...UPLOAD_DEFAULTS, name: "Shoe" }, jpeg());
    expect(fd.get("name")).toBe("Shoe");
    expect(fd.get("file")).toBeInstanceOf(File);
    expect(fd.get("brand")).toBeNull();
    expect(fd.get("price")).toBeNull();
  });

  it("includes provided optionals", () => {
    const fd = buildUploadFormData(
      { name: "Shoe", brand: "Nike", category: "Men", description: "d", price: "1999" },
      jpeg(),
    );
    expect(fd.get("brand")).toBe("Nike");
    expect(fd.get("price")).toBe("1999");
  });
});

describe("isTerminal", () => {
  it("classifies job states", () => {
    expect(isTerminal("completed")).toBe(true);
    expect(isTerminal("failed")).toBe(true);
    expect(isTerminal("running")).toBe(false);
    expect(isTerminal("pending")).toBe(false);
  });
});

describe("JobProgress", () => {
  it("shows the live stage and percentage", () => {
    render(<JobProgress job={JOB} />);
    expect(screen.getByText(/Processing Upload/)).toBeInTheDocument();
    expect(screen.getByText(/40%/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("surfaces the error message when the job failed", () => {
    render(<JobProgress job={{ ...JOB, status: "failed", error: "worker exploded" }} />);
    expect(screen.getByText("worker exploded")).toBeInTheDocument();
  });
});
