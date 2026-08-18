import type { Store } from "@/lib/platform";

// Shell identity (tenant, user, stores) cached for the tab session so admin
// navigation shows the chrome instantly instead of refetching on every page.
// Cleared on logout and on any auth failure.
export type Identity = { tenantName?: string; userName?: string; stores: Store[]; activeStoreId: string };

let cache: Identity | null = null;

export const getIdentityCache = () => cache;
export const setIdentityCache = (value: Identity | null) => {
  cache = value;
};
