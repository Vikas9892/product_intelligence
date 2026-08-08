import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ImageCard } from "@/features/product/image-card";
import { productImageUrl } from "@/lib/api/endpoints/products";

const PRODUCT_ID = "11111111-1111-1111-1111-111111111111";

describe("ImageCard", () => {
  it("renders the product's image rather than a placeholder", () => {
    // Regression: this component used to render "Image not available" with the
    // copy "The API does not serve product images" — an apology in the UI for a
    // capability that had simply never been built.
    render(<ImageCard productId={PRODUCT_ID} alt="Aurora Runner Blue" />);

    const image = screen.getByRole("img", { name: "Aurora Runner Blue" });
    expect(image).toBeInTheDocument();
    // next/image routes through the optimizer, so the real target is the
    // decoded `url` parameter rather than the raw src.
    const src = image.getAttribute("src") ?? "";
    expect(decodeURIComponent(src)).toContain(`/products/${PRODUCT_ID}/image`);

    expect(screen.queryByText("Image not available")).not.toBeInTheDocument();
    expect(screen.queryByText(/does not serve product images/)).not.toBeInTheDocument();
  });

  it("falls back to a per-product message, not a claim about the API", () => {
    render(<ImageCard productId={PRODUCT_ID} />);

    // Simulate the browser failing to load it (404 for a product with no image).
    fireEvent.error(screen.getByRole("img"));

    expect(screen.getByText("No image for this product")).toBeInTheDocument();
    expect(screen.queryByText(/does not serve product images/)).not.toBeInTheDocument();
  });
});

describe("productImageUrl", () => {
  it("builds a same-origin path", () => {
    expect(productImageUrl(PRODUCT_ID)).toBe(`/api/v1/products/${PRODUCT_ID}/image`);
  });

  it("requests the thumbnail variant when asked", () => {
    expect(productImageUrl(PRODUCT_ID, { thumbnail: true })).toBe(
      `/api/v1/products/${PRODUCT_ID}/image?thumbnail=true`,
    );
  });
});
