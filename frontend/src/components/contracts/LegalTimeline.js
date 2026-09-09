import React, { useState } from "react";
import { CheckCircle2, Circle, ShieldAlert } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/context/AuthContext";
import { formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { P53 } from "@/constants/testIds";

/**
 * LegalTimeline — tahap legal MILIK PEMBELI (keputusan owner D4).
 *
 * Perbedaan dengan rantai legal lama di `deals`: di sini `akad_kredit` ADA (peristiwa yang
 * menentukan pada skema KPR) dan setiap tahap membawa GERBANG BUKTI-nya. Bila tahap belum
 * boleh dimajukan, layar menuliskan SEBABnya (dari server) alih-alih menyisakan tombol mati:
 * “DP belum terbayar”, “SP3K belum lengkap”, “kelebihan tanah belum lunas”, dan seterusnya.
 */
export default function LegalTimeline({ contract, onChanged }) {
  const { can } = useAuth();
  const mayManage = can("contracts", "manage");
  const [stage, setStage] = useState(null);
  const [form, setForm] = useState({ number: "", date: "", notary: "", place: "", note: "" });
  const [busy, setBusy] = useState(false);
  const gates = contract?.gates || {};
  const legal = contract?.legal || {};
  const order = contract?.legal_order || [];

  const open = (s) => {
    setForm({ number: "", date: "", notary: "", place: "", note: "" });
    setStage(s);
  };

  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/contracts/${contract.id}/legal/${stage}`, {
        number: form.number.trim() || undefined,
        date: form.date || undefined,
        notary: form.notary.trim() || undefined,
        place: form.place.trim() || undefined,
        note: form.note.trim() || undefined,
      });
      toast.success(`Tahap ${gates[stage]?.label || stage} tercatat.`);
      setStage(null);
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memajukan tahap legal.");
    } finally { setBusy(false); }
  };

  return (
    <section className="space-y-3 rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
      <div>
        <h3 className="section-title">Tahap legal pembeli</h3>
        <p className="text-xs text-muted-foreground">
          {contract?.scheme === "kpr"
            ? "Skema KPR: AJB menyusul AKAD KREDIT (bukan menunggu serah terima kunci)."
            : "Skema tunai: AJB menyusul pelunasan dan serah terima kunci (BAST)."}
          {contract?.shgb_months_after_ajb
            ? ` Sertifikat (SHGB) ±${contract.shgb_months_after_ajb} bulan sesudah AJB.`
            : ""}
        </p>
      </div>
      <ol className="space-y-2">
        {order.map((s) => {
          const g = gates[s] || {};
          const done = !!legal[s];
          return (
            <li key={s} data-testid={P53.legalStep} data-stage={s} data-done={done}
              className="flex flex-wrap items-start justify-between gap-2 rounded-lg border bg-background p-3">
              <div className="min-w-0">
                <p className="flex items-center gap-2 text-sm font-medium">
                  {done ? <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                    : <Circle className="h-4 w-4 text-muted-foreground" />}
                  {g.label || s}
                </p>
                {done ? (
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {legal[s].number ? `${legal[s].number} · ` : ""}
                    {legal[s].date ? formatDateWIB(legal[s].date) : ""}
                    {legal[s].notary ? ` · notaris ${legal[s].notary}` : ""}
                  </p>
                ) : (g.blocks || []).length ? (
                  <p data-testid={P53.legalBlocked}
                    className="mt-0.5 flex items-start gap-1.5 text-xs text-amber-700">
                    <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    <span>{g.blocks.map((b) => b.detail).join(" ")}</span>
                  </p>
                ) : (
                  <p className="mt-0.5 text-xs text-emerald-700">Semua syarat sudah terpenuhi.</p>
                )}
              </div>
              {!done && mayManage ? (
                <Button data-testid={`${P53.legalBtn}-${s}`} size="sm" variant="outline"
                  disabled={!g.ok} onClick={() => open(s)}>
                  Catat {g.label || s}
                </Button>
              ) : null}
            </li>
          );
        })}
      </ol>
      {!mayManage ? (
        <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
          Memajukan tahap legal adalah wewenang manajer (pemisahan tugas dari yang
          mengajukan) — karena itu tombolnya tidak ditampilkan untuk peran Anda.
        </p>
      ) : null}

      <Dialog open={!!stage} onOpenChange={(v) => !v && setStage(null)}>
        <DialogContent data-testid={P53.legalDialog} className="max-w-md bg-background">
          <DialogHeader>
            <DialogTitle>Catat {gates[stage]?.label || stage}</DialogTitle>
            <DialogDescription>
              Nomor dibiarkan kosong = sistem yang menomori. Tanggal kosong = hari ini.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="lg-num">Nomor akta / dokumen (opsional)</Label>
              <Input id="lg-num" className="bg-background" value={form.number}
                onChange={(e) => setForm((f) => ({ ...f, number: e.target.value }))} />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="lg-date">Tanggal</Label>
                <Input id="lg-date" type="date" className="bg-background" value={form.date}
                  onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lg-notary">Notaris (bila ada)</Label>
                <Input id="lg-notary" className="bg-background" value={form.notary}
                  onChange={(e) => setForm((f) => ({ ...f, notary: e.target.value }))} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lg-note">Catatan</Label>
              <Textarea id="lg-note" rows={2} className="bg-background" value={form.note}
                onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setStage(null)}>Batal</Button>
            <Button data-testid={P53.legalSubmit} onClick={submit} disabled={busy}>
              {busy ? "Menyimpan…" : "Simpan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
