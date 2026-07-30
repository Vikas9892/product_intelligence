import { Compass } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

/**
 * 404 boundary (Next.js `not-found.tsx`). Rendered for unmatched routes.
 */
export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
      <div className="bg-muted text-muted-foreground flex size-12 items-center justify-center rounded-full">
        <Compass className="size-6" />
      </div>
      <div className="space-y-1">
        <p className="text-muted-foreground text-sm font-medium">404</p>
        <h1 className="text-xl font-semibold">Page not found</h1>
        <p className="text-muted-foreground max-w-sm text-sm">
          The page you are looking for does not exist or has moved.
        </p>
      </div>
      <Button asChild>
        <Link href="/">Back to dashboard</Link>
      </Button>
    </div>
  );
}
