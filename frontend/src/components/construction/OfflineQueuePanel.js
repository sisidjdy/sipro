import React from "react";
import { CloudOff, Send, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useOffline } from "@/context/OfflineContext";
import { useReference } from "@/context/ReferenceContext";
import * as sync from "@/services/offlineSync";
import { fromNow } from "@/utils/formatters";
import { OFFLINE } from "@/constants/testIds";

/**
 * Antrean kerja tersimpan di perangkat (Fase 35, diperluas Fase 50B).
 *
 * Mandor harus bisa MELIHAT apa yang belum terkirim, kenapa gagal, dan mencoba lagi.
 * Tanpa panel ini "tersimpan otomatis" cuma janji yang tidak bisa diperiksa.
 *
 * Fase 50B: panel yang SAMA sekarang juga membawa absensi, buku harian, dan temuan punch
 * list. Karena pekerjaan itu tidak punya kode langkah/unit seperti pengajuan hasil kerja,
 * setiap pekerjaan antrean membawa `title` berbahasa manusia — mandor tidak bisa menilai
 * antrean dari id.
 *
 * Label jenis & status diambil dari SSOT `/api/reference`
 * (`offline_queue_kind` / `offline_queue_status`) — bukan peta hardcode.
 */
export default function OfflineQueuePanel({ kinds = null }) {
  const { jobs, online, refresh } = useOffline();
  const { labelOf } = useReference();
  const rows = kinds ? jobs.filter((j) => kinds.includes(j.kind)) : jobs;
  if (!rows.length) return null;

  const retry = async (id) => { await sync.retry(id); await refresh(); };
  const drop = async (id) => { await sync.remove(id); await refresh(); };

  return (
    <div data-testid={OFFLINE.queuePanel}
      className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-amber-900">
      <p className="flex items-center gap-1.5 text-xs font-semibold">
        <CloudOff className="h-3.5 w-3.5" />
        Tersimpan di perangkat ({rows.length}) — belum sampai ke server
      </p>
      <p className="mt-0.5 text-[11px]">
        {online
          ? "Sedang dikirim otomatis. Anda juga bisa menekan “Kirim” pada barisnya."
          : "Akan terkirim sendiri begitu sinyal kembali. Aman ditutup — data tidak hilang."}
      </p>
      <div className="mt-2 space-y-2">
        {rows.map((j) => (
          <div key={j.id} data-testid={OFFLINE.queueRow} data-status={j.status}
            data-kind={j.kind}
            className="rounded-lg border bg-card p-2 text-[11px] text-foreground shadow-[var(--shadow-card)]">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="font-semibold">
                  {labelOf("offline_queue_kind", j.kind)}
                  {j.unit_code ? ` · ${j.unit_code}` : ""}
                  {j.step_code ? (
                    <>
                      {" · "}
                      <span className="font-mono text-[10px]">{j.step_code}</span>
                    </>
                  ) : null}
                  {j.name ? ` ${j.name}` : ""}
                  {j.title ? ` · ${j.title}` : ""}
                </p>
                <p className="text-muted-foreground">
                  {labelOf("offline_queue_status", j.status)} · dibuat {fromNow(j.created_at)}
                  {(j.photos || []).length ? ` · ${j.photos.length} foto bukti ikut tersimpan` : ""}
                  {j.attempts ? ` · ${j.attempts}× dicoba` : ""}
                </p>
                {j.last_error ? (
                  <p className={j.status === "rejected" ? "text-rose-700" : "text-amber-700"}>
                    {j.last_error}
                  </p>
                ) : null}
              </div>
              <div className="flex gap-1.5">
                <Button data-testid={OFFLINE.queueRetry} size="sm" variant="outline"
                  className="h-7 px-2 text-[11px]" onClick={() => retry(j.id)}>
                  <Send className="mr-1 h-3 w-3" /> Kirim
                </Button>
                {j.status === "rejected" ? (
                  <Button data-testid={OFFLINE.queueRemove} size="sm" variant="ghost"
                    className="h-7 px-2 text-[11px] text-rose-700" onClick={() => drop(j.id)}>
                    <Trash2 className="mr-1 h-3 w-3" /> Buang
                  </Button>
                ) : null}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
