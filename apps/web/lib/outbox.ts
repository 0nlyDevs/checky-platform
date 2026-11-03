"use client";

/**
 * « À envoyer »: checks made with no network, kept on this device (IndexedDB, so a photo fits) and
 * run by Vérifier when the network returns. Nothing else is queued: other writes are refused offline.
 */
import { useMemo, useSyncExternalStore } from "react";

export type OutboxEntry = { id: string; ws: string; at: string; text?: string; photo?: Blob; name?: string; sourceId?: string };

const DB = "checky-outbox";
const STORE = "checks";
const listeners = new Set<() => void>();
let snapshot: OutboxEntry[] = [];

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "id" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function run<T>(mode: IDBTransactionMode, work: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const req = work(db.transaction(STORE, mode).objectStore(STORE));
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function refresh() {
  try {
    const all = (await run("readonly", (s) => s.getAll())) as OutboxEntry[];
    snapshot = all.sort((a, b) => a.at.localeCompare(b.at));
  } catch {
    snapshot = [];
  }
  listeners.forEach((f) => f());
}

export async function addToOutbox(entry: Omit<OutboxEntry, "id" | "at">) {
  const id = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  await run("readwrite", (s) => s.put({ ...entry, id, at: new Date().toISOString() }));
  await refresh();
}

export async function removeFromOutbox(id: string) {
  await run("readwrite", (s) => s.delete(id)).catch(() => null);
  await refresh();
}

export async function updateOutbox(entry: OutboxEntry) {
  await run("readwrite", (s) => s.put(entry));
  await refresh();
}

let loaded = false;
function subscribe(onChange: () => void) {
  listeners.add(onChange);
  if (!loaded) {
    loaded = true;
    void refresh();
  }
  return () => listeners.delete(onChange);
}

const EMPTY: OutboxEntry[] = [];
/** The checks waiting on this device for one newsroom, oldest first. */
export function useOutbox(ws: string): OutboxEntry[] {
  const all = useSyncExternalStore(
    subscribe,
    () => snapshot,
    () => EMPTY,
  );
  return useMemo(() => all.filter((e) => e.ws === ws), [all, ws]);
}
