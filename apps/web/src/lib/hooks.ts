"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { get } from "./api";
import type { Me, Settings } from "./types";

export const useMe = () => useQuery({ queryKey: ["me"], queryFn: () => get<Me>("/auth/me"), staleTime: 60_000 });
/** What the signed in person may do. A viewer looks at everything and changes nothing, so the screens switch off what the server would refuse. */
export function useRole() {
  const me = useMe();
  const role = me.data?.role;
  return { role, owner: role === "owner", canWrite: role === "owner" || role === "approver", known: !!role, user: me.data?.user ?? "" };
}
export const READ_ONLY = "This sign in is read only";
export const useSettings = () => useQuery({ queryKey: ["settings"], queryFn: () => get<Settings>("/settings") });

/** Listen to the live event stream. Any event refreshes the numbers on screen, at most once a second. */
export function useLiveRefresh() {
  const qc = useQueryClient();
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const es = new EventSource("/api/events/stream");
    es.onmessage = () => {
      if (timer) return;
      timer = setTimeout(() => {
        timer = null;
        qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "me" });
      }, 1000);
    };
    return () => {
      es.close();
      if (timer) clearTimeout(timer);
    };
  }, [qc]);
}
