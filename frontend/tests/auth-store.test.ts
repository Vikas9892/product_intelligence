import { beforeEach, describe, expect, it } from "vitest";

import { getApiKey } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  useAuthStore.getState().signOut();
});

describe("auth store", () => {
  it("is anonymous with no request header after sign out", () => {
    expect(useAuthStore.getState().status).toBe("anonymous");
    expect(getApiKey()).toBeNull();
  });

  it("signIn updates state, persists the key, and primes the request header", () => {
    useAuthStore.getState().signIn({ key: "pik_test_123456", role: "admin", scope: "session" });

    const state = useAuthStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.role).toBe("admin");
    expect(state.keyPrefix).toBe("pik_test_123");
    expect(getApiKey()).toBe("pik_test_123456");
    expect(window.sessionStorage.getItem("pi.apiKey")).toBe("pik_test_123456");
  });

  it("hydrate restores a key persisted to local storage", () => {
    useAuthStore.getState().signIn({ key: "pik_persist_abc", scope: "local" });
    // Simulate a fresh page load: reset in-memory state, then hydrate.
    setApiKeyless();
    useAuthStore.getState().hydrate();

    expect(useAuthStore.getState().status).toBe("authenticated");
    expect(getApiKey()).toBe("pik_persist_abc");
  });

  it("signOut clears state, storage, and the request header", () => {
    useAuthStore.getState().signIn({ key: "pik_x_000000", scope: "local" });
    useAuthStore.getState().signOut();

    expect(useAuthStore.getState().apiKey).toBeNull();
    expect(getApiKey()).toBeNull();
    expect(window.localStorage.getItem("pi.apiKey")).toBeNull();
  });
});

function setApiKeyless() {
  useAuthStore.setState({ status: "loading", apiKey: null, keyPrefix: null });
}
