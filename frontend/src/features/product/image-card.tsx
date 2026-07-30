import { ImageOff } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

/**
 * Image placeholder. The backend stores processed images on disk but does not
 * serve them over HTTP (no static mount / image endpoint), so there is no URL
 * to render. Shown honestly rather than faking an image.
 */
export function ImageCard() {
  return (
    <Card>
      <CardContent className="flex aspect-square flex-col items-center justify-center gap-2 p-6 text-center">
        <div className="bg-muted text-muted-foreground flex size-14 items-center justify-center rounded-full">
          <ImageOff className="size-7" />
        </div>
        <p className="text-sm font-medium">Image not available</p>
        <p className="text-muted-foreground max-w-[15rem] text-xs">
          The API does not serve product images, so the uploaded image cannot be displayed here.
        </p>
      </CardContent>
    </Card>
  );
}
