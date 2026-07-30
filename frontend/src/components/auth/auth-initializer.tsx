"use client";

import { useEffect } from "react";

import { useAuthStore } from "@/stores/auth-store";

/**
 * Hydrates the auth store from persisted storage exactly once on the client and
 * primes the API request header. Renders nothing. Mounted in the provider tree
 * so any persisted key is active before the first data request.
 */
export function AuthInitializer() {
  const hydrate = useAuthStore((state) => state.hydrate);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  return null;
}
