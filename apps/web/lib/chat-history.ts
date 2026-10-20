"use client";

import type { AskResponse } from "./api";

/** Conversations kept on this device (IndexedDB), per account and repository, for ten years.
 *  Nothing leaves the device; clearing the browser's site data (or the app's data) removes them. */

export type StoredMessage = { id: string; role: "user" | "sherpa"; text: string; meta?: AskResponse; voice?: boolean };
export type Chat = {
  id: string;
  userId: string;
  repoId: string;
  title: string;
  createdAt: number; // ms
  updatedAt: number;
  expiresAt: number;
  messages: StoredMessage[];
};

export const RETENTION_MS = 10 * 365.25 * 24 * 3600 * 1000; // ten years
const DB = "sherpa";
const STORE = "chats";

let dbp: Promise<IDBDatabase> | null = null;

function db(): Promise<IDBDatabase> {
  dbp ??= new Promise((resolve, reject) => {
    const r = indexedDB.open(DB, 1);
    r.onupgradeneeded = () => {
      const s = r.result.createObjectStore(STORE, { keyPath: "id" });
      s.createIndex("owner", ["userId", "repoId"]);
    };
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
  dbp.catch(() => (dbp = null));
  // ask the browser not to evict this data under storage pressure (best effort)
  navigator.storage?.persist?.().catch(() => {});
  return dbp;
}

function tx<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return db().then(
    (d) =>
      new Promise<T>((resolve, reject) => {
        const req = fn(d.transaction(STORE, mode).objectStore(STORE));
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      })
  );
}

/** This account's chats about this repo, newest first. Expired ones are deleted on the way. */
export async function listChats(userId: string, repoId: string): Promise<Chat[]> {
  const all = await tx<Chat[]>("readonly", (s) => s.index("owner").getAll([userId, repoId]));
  const now = Date.now();
  const expired = all.filter((c) => c.expiresAt <= now);
  expired.forEach((c) => deleteChat(c.id).catch(() => {}));
  return all.filter((c) => c.expiresAt > now).sort((a, b) => b.updatedAt - a.updatedAt);
}

export async function saveChat(c: Omit<Chat, "updatedAt" | "expiresAt" | "title"> & { title?: string }): Promise<void> {
  const now = Date.now();
  const first = c.messages.find((m) => m.role === "user")?.text ?? "New chat";
  await tx("readwrite", (s) =>
    s.put({ ...c, title: c.title || first.slice(0, 80), updatedAt: now, expiresAt: now + RETENTION_MS })
  );
}

export const deleteChat = (id: string) => tx("readwrite", (s) => s.delete(id));

export const historySupported = () => typeof indexedDB !== "undefined";
