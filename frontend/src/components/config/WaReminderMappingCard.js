import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { BellRing, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import StatusPill from "@/components/patterns/StatusPill";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { P97 } from "@/constants/testIds";

/** Template mana untuk pengingat apa — dulu tersebar di 5 kunci setting di tab lain (WA-14). */
export default function WaReminderMappingCard({ templates, canManage, refreshKey }) {
  const { labelOf } = useReference();
  const [rows, setRows] = useState(null);
  const [draft, setDraft] = useState({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/wa-templates/reminder-mapping").then((r) => { setRows(r.data.data); setDraft({}); })
      .catch((e) => toast.error(e?.response?.data?.detail || "Gagal memuat pemetaan pengingat."));
  }, []);
  useEffect(() => { load(); }, [load, refreshKey]);

  const approved = (templates || []).filter((t) => t.status === "approved");
  const dirty = Object.keys(draft).length > 0;

  const save = async () => {
    setBusy(true);
    try {
      const r = await api.put("/wa-templates/reminder-mapping", { mapping: draft });
      toast.success(`Pemetaan ${r.data.changed.length} pengingat disimpan.`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan pemetaan.", { duration: 9000 }); }
    finally { setBusy(false); }
  };

  if (!rows) return null;
  return (
    <div data-testid={P97.tmplMappingCard} className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="flex items-center gap-1.5 text-sm font-semibold"><BellRing className="h-4 w-4 text-primary" /> Template untuk pengingat otomatis</p>
          <p className="text-xs text-muted-foreground">Pengingat hanya boleh memakai template yang <b>disetujui</b>. Variabel template harus tersedia pada jenis pengingatnya (nama, termin, nominal, tanggal, unit, bagian, sisa, bulan, terlama).</p>
        </div>
        {canManage ? (
          <Button size="sm" data-testid={P97.tmplMappingSave} onClick={save} disabled={!dirty || busy}>
            <Save className="mr-1 h-3.5 w-3.5" /> {busy ? "Menyimpan…" : "Simpan pemetaan"}
          </Button>
        ) : null}
      </div>
      <div className="divide-y">
        {rows.map((r) => {
          const value = draft[r.kind] ?? r.template_code ?? "";
          return (
            <div key={r.kind} data-testid={P97.tmplMappingRow} data-kind={r.kind} className="grid items-center gap-2 py-2 sm:grid-cols-[1fr_1.2fr_auto]">
              <div>
                <p className="text-sm font-medium">{r.label}</p>
                <p className="text-[11px] text-muted-foreground">{r.help}</p>
              </div>
              {canManage ? (
                <Select value={value} onValueChange={(v) => setDraft((d) => ({ ...d, [r.kind]: v }))}>
                  <SelectTrigger data-testid={P97.tmplMappingSelect} aria-label={`Template untuk ${r.label}`} className="h-9"><SelectValue placeholder="Pilih template" /></SelectTrigger>
                  <SelectContent>
                    {approved.map((t) => <SelectItem key={t.code} value={t.code}>{t.name} · {t.code}</SelectItem>)}
                  </SelectContent>
                </Select>
              ) : <p className="text-sm">{r.template_name || r.template_code}</p>}
              <div className="flex items-center gap-1.5 text-xs">
                {r.missing ? <span className="rounded bg-rose-50 px-1.5 py-0.5 text-rose-700">template tidak ada</span>
                  : <StatusPill status={r.template_status} group="wa_template_status" />}
                {!r.missing && r.meta_status ? <span className="text-muted-foreground">Meta: {labelOf("wa_meta_template_status", r.meta_status)}</span> : null}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
