"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, tokenStore } from "../lib/api";

type User = { id: string; email: string; name: string } | null;

const Ctx = createContext<{
  user: User;
  loading: boolean;
  signIn: (token: string) => Promise<void>;
  signOut: () => void;
}>({ user: null, loading: true, signIn: async () => {}, signOut: () => {} });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!tokenStore.get()) return setLoading(false);
    api.me().then(setUser).catch(() => tokenStore.clear()).finally(() => setLoading(false));
  }, []);

  const signIn = useCallback(async (token: string) => {
    tokenStore.set(token);
    setUser(await api.me());
  }, []);

  const signOut = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  return <Ctx.Provider value={{ user, loading, signIn, signOut }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
