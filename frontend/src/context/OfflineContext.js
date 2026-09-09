import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import * as sync from "@/services/offlineSync";

/**
 * OfflineContext — satu sumber kebenaran soal "sedang offline?" dan "apa yang belum
 * terkirim?" (Fase 35).
 *
 * Dipakai spanduk global, Papan Mandor, dan dialog pengajuan supaya pesan ke mandor
 * konsisten: pekerjaan tidak pernah hilang, dan tidak ada yang mengaku terkirim
 * sebelum server benar-benar menerimanya.
 */
const Ctx = createContext({
  online: true, jobs: [], pending: 0, rejected: 0, refresh: () => {}, flush: () => {},
});

const RETRY_MS = 30000;

export function OfflineProvider({ children }) {
  const [online, setOnline] = useState(sync.isOnline());
  const [jobs, setJobs] = useState([]);

  const refresh = useCallback(async () => {
    setJobs(await sync.list());
  }, []);

  const flush = useCallback(async ({ quiet = false } = {}) => {
    const res = await sync.flush();
    if (!quiet && res.sent) {
      toast.success(`${res.sent} pekerjaan tersimpan berhasil dikirim ke server.`);
    }
    if (!quiet && res.failed) {
      toast.warning(`${res.failed} pekerjaan belum terkirim — lihat antrean di Papan Mandor.`);
    }
    await refresh();
    return res;
  }, [refresh]);

  useEffect(() => {
    refresh();
    const unsub = sync.subscribe(refresh);
    const goOnline = () => {
      setOnline(true);
      flush();
    };
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    const timer = setInterval(() => {
      setOnline(sync.isOnline());
      if (sync.isOnline()) flush({ quiet: true });
    }, RETRY_MS);
    return () => {
      unsub();
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
      clearInterval(timer);
    };
  }, [refresh, flush]);

  const value = useMemo(() => {
    const pending = jobs.filter((j) => j.status === "pending" || j.status === "sending").length;
    const rejected = jobs.filter((j) => j.status === "rejected").length;
    return { online, jobs, pending, rejected, refresh, flush };
  }, [online, jobs, refresh, flush]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useOffline = () => useContext(Ctx);
