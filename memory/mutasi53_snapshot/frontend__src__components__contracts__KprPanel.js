import React, { useState } from "react";
import { Banknote, CheckCircle2, Circle, XCircle } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import EvidenceUploader from "@/components/patterns/EvidenceUploader";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { useAuth } from "@/context/AuthContext";
import { formatDateWIB, formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { P53 } from "@/constants/testIds";

/**
 * KprPanel — sub-alur KPR: berkas → bank → appraisal → **SP3K** → **AKAD KREDIT** → pencairan.
 *
 * Sebelum Fase 53 tidak ada tempat menyimpan SP3K/akad/pencairan, sehingga “sudah akad atau
 * belum” hanya ada di kepala orang. Dua gerbang bukti yang dipaksakan server dan dijelaskan
 * di layar ini: **SP3K wajib berkas + plafon yang DISETUJUI bank**, dan **akad kredit wajib
 * SP3K sah serta kelebihan tanah sudah lunas** (ketentuan SPKT milik owner).
 */
const NEEDS = {
  sp3k: ["number", "plafon", "tenor_months", "rate", "valid_until", "file"],
  akad_kredit: ["date", "notary", "place", "file"],
  pencairan: ["date", "amount", "file"],
  appraisal: ["date", "amount", "note"],
  diajukan_ke_bank: ["bank", "note"],
  berkas_lengkap: ["note"],
};

export default function KprPanel({ contract, onChanged }) {
  const { can } = useAuth();
  const mayUpdate = can("financing", "update");
  const kpr = contract?.kpr || {};
  const app = kpr.application || {};
  const [stage, setStage] = useState(null);
  const [reject, setReject] = useState(false);
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);

  if (!kpr.applicable) return null;

  const openStage = (s) => { setForm({}); setStage(s); };
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/contracts/${contract.id}/kpr/stage/${stage}`, {
        number: form.number || undefined,
        date: form.date || undefined,
        plafon: form.plafon ? Number(form.plafon) : undefined,
        tenor_months: form.tenor_months ? Number(form.tenor_months) : undefined,
        rate: form.rate ? Number(form.rate) : undefined,
        valid_until: form.valid_until || undefined,
        bank: form.bank || undefined,
        amount: form.amount ? Number(form.amount) : undefined,
        notary: form.notary || undefined,
        place: form.place || undefined,
        file_id: form.file_id || undefined,
        note: form.note || undefined,
      });
      toast.success("Tahap KPR diperbarui.");
      setStage(null);
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memajukan tahap KPR.");
    } finally { setBusy(false); }
  };

  const doReject = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/contracts/${contract.id}/kpr/reject`, {
        reason: form.reason || "", file_id: form.file_id || undefined,
      });
      const r = res.data.data?.rejection || {};
      toast.success(`Penolakan bank dicatat. Usul refund booking fee ${r.refund_pct}% `
        + `(${formatIDR(r.refund_amount)}).`);
      setReject(false);
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mencatat penolakan bank.");
    } finally { setBusy(false); }
  };

  const fields = NEEDS[stage] || ["note"];

  return (
    <section data-testid={P53.kprPanel} className="space-y-3 rounded-lg border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="flex items-center gap-2 font-heading text-base font-semibold">
            <Banknote className="h-4 w-4" /> Pengajuan KPR
          </h3>
          <p className="text-xs text-muted-foreground">
            Bank {app.bank_name || "belum diisi"}
            {app.approved_plafon ? ` · plafon disetujui ${formatIDR(app.approved_plafon)}` : ""}
            {app.tenor_months ? ` · tenor ${app.tenor_months} bulan` : ""}
          </p>
        </div>
        {mayUpdate && app.kpr_stage !== "ditolak" ? (
          <Button data-testid={P53.kprRejectBtn} size="sm" variant="outline"
            onClick={() => { setForm({}); setReject(true); }}>
            <XCircle className="mr-1.5 h-3.5 w-3.5" /> Bank menolak
          </Button>
        ) : null}
      </div>

      {app.kpr_stage === "ditolak" ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
          <p className="font-medium">KPR ditolak bank</p>
          <p className="mt-0.5 text-xs">{app.rejection?.note}</p>
          <p className="mt-1 text-xs">
            Usulan refund booking fee {app.rejection?.refund_pct}% ={" "}
            {formatIDR(app.rejection?.refund_amount)} — sesuai ketentuan SPR.
          </p>
        </div>
      ) : null}

      <ol className="space-y-2">
        {(kpr.stages || []).map((s) => (
          <li key={s.stage} data-testid={P53.kprStage} data-stage={s.stage}
            data-done={s.done}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-background p-3">
            <p className="flex items-center gap-2 text-sm">
              {s.done ? <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                : <Circle className="h-4 w-4 text-muted-foreground" />}
              <span className={s.current ? "font-medium" : ""}>{s.label}</span>
              {s.current ? (
                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                  tahap sekarang
                </span>
              ) : null}
            </p>
            {mayUpdate && !s.done && kpr.next_stage === s.stage ? (
              <Button data-testid={`${P53.kprBtn}-${s.stage}`} size="sm" variant="outline"
                onClick={() => openStage(s.stage)}>Catat {s.label}</Button>
            ) : null}
          </li>
        ))}
      </ol>
      {app.sp3k?.file_id ? (
        <p className="text-xs text-muted-foreground">
          SP3K {app.sp3k.number || ""} · {app.sp3k.date ? formatDateWIB(app.sp3k.date) : ""}
          {" "}· berkas bukti tersimpan.
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">
          Akad kredit membutuhkan SP3K bank beserta BERKASnya — tanpa itu tahap akad tidak
          bisa dimajukan (dan itu memang aturannya, bukan tombol yang rusak).
        </p>
      )}

      {/* dialog tahap */}
      <Dialog open={!!stage} onOpenChange={(v) => !v && setStage(null)}>
        <DialogContent data-testid={P53.kprDialog}
          className="max-h-[85vh] max-w-md overflow-y-auto bg-background">
          <DialogHeader>
            <DialogTitle>Catat tahap KPR</DialogTitle>
            <DialogDescription>
              Isi bukti yang diminta tahap ini. Server menolak tahap tanpa bukti — supaya
              “sudah SP3K” dan “sudah akad” tidak pernah hanya klaim.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            {fields.includes("bank") ? (
              <div className="space-y-1.5">
                {/* Bank dipilih dari Kamus Data (`financing_bank`), BUKAN diketik bebas.
                    Temuan gate `audit_forms_deep`: satu-satunya field relasi di Fase 53
                    yang masih input bebas. Akibat nyata bila dibiarkan — "BTN", "btn",
                    "Bank BTN", "BTN " menjadi empat bank berbeda, sehingga rekap KPR per
                    bank (dan pencocokan SP3K) memecah satu bank menjadi banyak baris.
                    Grup ini `dynamic`, jadi bank yang belum terdaftar tetap bisa
                    ditambahkan lewat "Nilai baru…" — tanpa membuka pintu salah ketik massal. */}
                <Label htmlFor="kpr-bank">Bank</Label>
                <ReferenceSelect group="financing_bank" testId="kpr-bank"
                  value={form.bank || ""} onChange={(v) => set("bank", v)}
                  placeholder="Pilih bank penyalur KPR…" />
              </div>
            ) : null}
            {fields.includes("number") ? (
              <div className="space-y-1.5">
                <Label htmlFor="kpr-num">Nomor SP3K</Label>
                <Input id="kpr-num" className="bg-background" value={form.number || ""}
                  onChange={(e) => set("number", e.target.value)} />
              </div>
            ) : null}
            {fields.includes("plafon") ? (
              <div className="space-y-1.5">
                <Label htmlFor="kpr-plafon">Plafon DISETUJUI bank (wajib)</Label>
                <Input id="kpr-plafon" inputMode="numeric" className="bg-background"
                  value={form.plafon || ""} onChange={(e) => set("plafon", e.target.value)} />
              </div>
            ) : null}
            {fields.includes("tenor_months") ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="kpr-tenor">Tenor (bulan)</Label>
                  <Input id="kpr-tenor" inputMode="numeric" className="bg-background"
                    value={form.tenor_months || ""}
                    onChange={(e) => set("tenor_months", e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="kpr-rate">Bunga (%/tahun)</Label>
                  <Input id="kpr-rate" inputMode="decimal" className="bg-background"
                    value={form.rate || ""} onChange={(e) => set("rate", e.target.value)} />
                </div>
              </div>
            ) : null}
            {fields.includes("amount") ? (
              <div className="space-y-1.5">
                <Label htmlFor="kpr-amt">Nilai (Rp)</Label>
                <Input id="kpr-amt" inputMode="numeric" className="bg-background"
                  value={form.amount || ""} onChange={(e) => set("amount", e.target.value)} />
              </div>
            ) : null}
            {fields.includes("date") || fields.includes("valid_until") ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="kpr-date">Tanggal</Label>
                  <Input id="kpr-date" type="date" className="bg-background"
                    value={form.date || ""} onChange={(e) => set("date", e.target.value)} />
                </div>
                {fields.includes("valid_until") ? (
                  <div className="space-y-1.5">
                    <Label htmlFor="kpr-valid">Berlaku sampai</Label>
                    <Input id="kpr-valid" type="date" className="bg-background"
                      value={form.valid_until || ""}
                      onChange={(e) => set("valid_until", e.target.value)} />
                  </div>
                ) : null}
              </div>
            ) : null}
            {fields.includes("notary") ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="kpr-notary">Notaris</Label>
                  <Input id="kpr-notary" className="bg-background" value={form.notary || ""}
                    onChange={(e) => set("notary", e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="kpr-place">Tempat akad</Label>
                  <Input id="kpr-place" className="bg-background" value={form.place || ""}
                    onChange={(e) => set("place", e.target.value)} />
                </div>
              </div>
            ) : null}
            {fields.includes("file") ? (
              <div className="space-y-1.5">
                <Label>Berkas bukti {stage === "sp3k" ? "(WAJIB)" : ""}</Label>
                <EvidenceUploader ownerType="contract" ownerId={contract.id} max={1}
                  value={form.files || []}
                  onChange={(ids) => setForm((f) => ({ ...f, files: ids,
                    file_id: ids[0] || undefined }))} />
                {form.file_id ? (
                  <p className="text-xs text-emerald-700">Berkas terunggah.</p>
                ) : null}
              </div>
            ) : null}
            <div className="space-y-1.5">
              <Label htmlFor="kpr-note">Catatan</Label>
              <Textarea id="kpr-note" rows={2} className="bg-background" value={form.note || ""}
                onChange={(e) => set("note", e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setStage(null)}>Batal</Button>
            <Button data-testid={P53.kprSubmit} onClick={submit} disabled={busy}>
              {busy ? "Menyimpan…" : "Simpan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* dialog penolakan bank */}
      <Dialog open={reject} onOpenChange={setReject}>
        <DialogContent className="max-w-md bg-background">
          <DialogHeader>
            <DialogTitle>Bank menolak pengajuan KPR</DialogTitle>
            <DialogDescription>
              Alasan minimal 10 huruf — dibaca pembeli & tim saat memutuskan langkah berikut
              (ganti bank, ganti skema, atau lepas unit).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Textarea rows={3} className="bg-background" value={form.reason || ""}
              placeholder="mis. penghasilan tidak memenuhi rasio angsuran menurut bank"
              onChange={(e) => set("reason", e.target.value)} />
            <EvidenceUploader ownerType="contract" ownerId={contract.id} max={1}
              label="Lampirkan surat penolakan (opsional)" value={form.files || []}
              onChange={(ids) => setForm((f) => ({ ...f, files: ids,
                file_id: ids[0] || undefined }))} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReject(false)}>Batal</Button>
            <Button onClick={doReject} disabled={busy || (form.reason || "").trim().length < 10}>
              {busy ? "Menyimpan…" : "Catat penolakan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
