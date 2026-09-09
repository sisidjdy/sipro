import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FileText, Settings2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { OMNI, P97 } from "@/constants/testIds";

/**
 * Lead WA › Template: HANYA daftar/pemilih. Isi, variabel, contoh, pengajuan Meta, dan
 * pemetaan pengingat diatur di satu tempat: Pusat Konfigurasi › Integrasi WhatsApp › Template
 * (audit WA-14 / keputusan K-1). Dua tempat untuk satu keputusan = sumber kebingungan.
 */
export default function TemplatesPanel() {
  const { labelOf } = useReference();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { setRows((await api.get("/wa-templates")).data.data || []); }
    catch (e) { setError(e?.response?.data?.detail || "Gagal memuat template."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const usable = rows.filter((t) => t.status === "approved");
  const others = rows.filter((t) => t.status !== "approved");

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
        <p className="text-sm text-muted-foreground">
          <b>{usable.length}</b> template siap pakai (disetujui) · {others.length} menunggu/ditolak.
          Template dibuat dan diubah di Pusat Konfigurasi supaya isi, status Meta, dan pemetaan pengingat tidak terpecah.
        </p>
        <Button asChild size="sm" variant="outline" data-testid={P97.tmplPickerLink}>
          <Link to="/config?tab=whatsapp&sub=templates"><Settings2 className="mr-1.5 h-4 w-4" /> Kelola template</Link>
        </Button>
      </div>
      {!rows.length ? (
        <EmptyState icon={FileText} title="Belum ada template" description="Buat template WA di Pusat Konfigurasi › Integrasi WhatsApp › Template." />
      ) : (
        <div className="grid gap-2 md:grid-cols-2">
          {rows.map((t) => (
            <div key={t.id} data-testid={OMNI.tmplRow} data-code={t.code} className={`rounded-xl border bg-card p-3 shadow-[var(--shadow-card)] ${t.status !== "approved" ? "opacity-70" : ""}`}>
              <div className="flex items-center gap-2">
                <p className="font-medium">{t.name}</p>
                <StatusPill status={t.status || "pending"} group="wa_template_status" />
              </div>
              <p className="text-[11px] text-muted-foreground">kode: {t.code} · {labelOf("wa_template_category", t.category)} · Meta: {labelOf("wa_meta_template_status", t.meta_status || "NOT_SUBMITTED")}</p>
              {t.status === "rejected" && t.meta_reason ? (
                <p data-testid={P97.tmplRejectReason} className="mt-1 text-[11px] text-rose-700">Alasan Meta: {t.meta_reason}</p>
              ) : null}
              <p className="mt-2 whitespace-pre-line rounded-lg bg-secondary p-2 text-xs text-secondary-foreground">{t.body}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
