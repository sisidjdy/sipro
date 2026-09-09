import React, { useCallback, useEffect, useState } from "react";
import { Download, FilePlus2, FileText } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { useAuth } from "@/context/AuthContext";
import { formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { P53 } from "@/constants/testIds";

/**
 * ContractDocuments — terbitkan & CETAK dokumen asli owner (SPR 3 varian + SPKT).
 *
 * Pertanyaan pemakai yang dijawab panel ini: *"bagaimana dokumen yang otomatis terbuat dari
 * data yang saya berikan? bagaimana saya bisa mencetaknya?"* Sebelum Fase 53 dokumen owner
 * belum pernah ada di sistem, dan satu-satunya tombol pembuat dokumen memaksa template
 * `SPR` generik. Sekarang:
 *   • template yang BOLEH diterbitkan datang dari server beserta SEBAB bila tidak boleh
 *     (mis. "SPR Cash bukan untuk kontrak KPR", "tidak ada kelebihan tanah → SPKT tidak
 *     perlu", "plafon KPR belum diisi");
 *   • angka di dokumen berasal dari kontrak — kalau ada biaya yang belum diisi, panel
 *     memperingatkan bahwa dokumen akan menulis "belum ditetapkan", bukan Rp 0;
 *   • setiap dokumen bisa langsung dibuka/dicetak sebagai PDF.
 */
export default function ContractDocuments({ contract, onChanged }) {
  const { can } = useAuth();
  const mayCreate = can("documents", "create");
  const [avail, setAvail] = useState(null);
  const [busy, setBusy] = useState("");
  const docs = contract?.documents || [];

  const load = useCallback(async () => {
    if (!contract?.id) return;
    try {
      const res = await api.get(`/contracts/${contract.id}/documents/available`);
      setAvail(res.data);
    } catch (e) {
      setAvail({ data: [], error: e?.response?.data?.detail || "Gagal memuat template." });
    }
  }, [contract?.id]);

  useEffect(() => { load(); }, [load]);

  const generate = async (code) => {
    setBusy(code);
    try {
      const res = await api.post(`/contracts/${contract.id}/documents`,
        { template_code: code });
      toast.success(`Dokumen ${res.data.data.doc_number} diterbitkan (draft).`);
      onChanged && onChanged();
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menerbitkan dokumen.");
    } finally { setBusy(""); }
  };

  const print = async (doc) => {
    setBusy(doc.id);
    try {
      const res = await api.get(`/documents/${doc.id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch {
      toast.error("Gagal membuka PDF dokumen.");
    } finally { setBusy(""); }
  };

  return (
    <section data-testid={P53.docPanel} className="space-y-3 rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="section-title">Dokumen kontrak</h3>
          <p className="text-xs text-muted-foreground">
            SPR & SPKT dibuat dari template ASLI (docs/source_templates) dengan angka kontrak
            ini — lalu bisa dicetak.
          </p>
        </div>
      </div>

      {mayCreate ? (
        <div className="flex flex-wrap gap-2">
          {(avail?.data || []).map((t) => (
            <div key={t.code} className="space-y-1">
              <Button data-testid={`${P53.docGenerateBtn}-${t.code}`} size="sm"
                variant={t.code === avail?.recommended_code ? "default" : "outline"}
                disabled={!t.can_generate || busy === t.code}
                onClick={() => generate(t.code)}>
                <FilePlus2 className="mr-1.5 h-3.5 w-3.5" />
                {busy === t.code ? "Menerbitkan…" : t.name}
                {t.existing ? ` (${t.existing})` : ""}
              </Button>
              {!t.can_generate ? (
                <p data-testid={`${P53.docBlocked}-${t.code}`}
                  className="max-w-[16rem] text-[11px] text-muted-foreground">
                  {(t.blocks || []).map((b) => b.detail).join(" ")}
                </p>
              ) : null}
              {t.can_generate && (t.warnings || []).length ? (
                <p data-testid={`${P53.docWarning}-${t.code}`}
                  className="max-w-[16rem] text-[11px] text-amber-700">
                  {t.warnings.join(" ")}
                </p>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
          Peran Anda boleh MEMBACA & mencetak dokumen, tetapi penerbitannya dipegang tim
          Sales/Marketing — karena itu tombol terbit tidak ditampilkan.
        </p>
      )}

      {docs.length ? (
        <div className="space-y-2">
          {docs.map((d) => (
            <div key={d.id} data-testid={P53.docRow} data-doc={d.template_code}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-background p-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{d.title}</p>
                <p className="font-mono text-xs text-muted-foreground">{d.doc_number}</p>
                <p className="text-[11px] text-muted-foreground">
                  Dibuat {formatDateTimeWIB(d.created_at)}
                  {d.template_version ? ` · template v${d.template_version}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <StatusPill status={d.status} group="document_status" />
                <Button data-testid={P53.docPrint} size="sm" variant="outline"
                  disabled={busy === d.id} onClick={() => print(d)}>
                  <Download className="mr-1.5 h-3.5 w-3.5" /> Cetak / PDF
                </Button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState icon={FileText} title="Belum ada dokumen diterbitkan"
          description="Terbitkan SPR sesuai skema kontrak; SPKT muncul bila ada kelebihan tanah." />
      )}
    </section>
  );
}
