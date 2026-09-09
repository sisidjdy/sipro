import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CalendarClock, Copy, Pencil, Plus, Trash2, Wand2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import MoneyText from "@/components/patterns/MoneyText";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { useReference } from "@/context/ReferenceContext";
import { formatDateWIB, formatIDR } from "@/utils/formatters";
import { P57 } from "@/constants/testIds";

const KOSONG = {
  name: "", kind: "cash_bertahap", active: true, is_default: false,
  applies_project_ids: [], note: "", terms: [],
};
const TERM_BARU = {
  label: "", basis: "percent", value: 0, due_mode: "offset_days", due_offset_days: 0,
  due_day: 7, grace_days: 0, event_code: "build_complete",
};

/**
 * SKEMA PEMBAYARAN (Fase 57A) — termin yang dulu terkunci di dalam kode sekarang menjadi
 * data yang disusun pemakai: DP nominal ATAU persen, berapa kali cicilan, tanggal berapa
 * jatuh temponya, berapa hari toleransinya, dan termin mana yang menunggu PERISTIWA.
 *
 * Dua hal yang panel ini menolak melakukan: (1) mengetik sendiri kalimat aturan jatuh tempo
 * (kalimatnya datang dari mesin, karena pembeli membacanya di dokumen), dan (2) menyimpan
 * skema yang tidak menagih seluruh harga — pratinjau menunjukkan selisihnya sebelum skema
 * itu menagih pembeli sungguhan.
 */
export default function PaymentSchemePanel() {
  const { labelOf } = useReference();
  const [rows, setRows] = useState([]);
  const [state, setState] = useState({ loading: true, error: "", reason: "" });
  const [kind, setKind] = useState("");
  const [form, setForm] = useState(null);
  const [preview, setPreview] = useState(null);
  const [price, setPrice] = useState(850000000);
  const [gen, setGen] = useState(null);
  const [projects, setProjects] = useState([]);

  const load = useCallback(async () => {
    setState({ loading: true, error: "", reason: "" });
    try {
      const res = await api.get("/payment-schemes", {
        params: { kind: kind || undefined } });
      setRows(res.data.data || []);
      setState({ loading: false, error: "", reason: res.data.reason || "" });
    } catch (e) {
      setState({ loading: false, reason: "",
        error: e?.response?.data?.detail || "Gagal memuat skema pembayaran." });
    }
  }, [kind]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    api.get("/projects", { params: { limit: 100 } })
      .then((r) => setProjects(r.data.data || []))
      .catch(() => setProjects([]));
  }, []);

  const simulate = useCallback(async (terms) => {
    // Termin yang MASIH DIISI (nama belum lengkap) bukan kesalahan — ia belum selesai.
    // Mengirimnya ke server hanya menghasilkan pesan validasi berisi jalur field
    // ("terms.0.label") yang tidak berarti apa pun bagi pemakai.
    const siap = (terms || []).filter((t) => (t.label || "").trim().length >= 3);
    const belum = (terms || []).length - siap.length;
    if (!siap.length) {
      setPreview({ rows: [], total: 0, balanced: false, blocks: [],
        note: "Beri nama setiap termin dahulu — pratinjau menunggu itu." });
      return;
    }
    try {
      const res = await api.post("/payment-schemes/simulate", {
        price: Number(price) || 0, terms: siap });
      const d = res.data.data;
      setPreview({ ...d, pending: belum });
    } catch (e) {
      setPreview({ rows: [], total: 0, balanced: false, blocks: [],
        note: e?.response?.data?.detail || "Pratinjau gagal." });
    }
  }, [price]);

  useEffect(() => { if (form) simulate(form.terms); }, [form, simulate]);

  const ubahTerm = (i, patch) => setForm((f) => ({
    ...f, terms: f.terms.map((t, idx) => (idx === i ? { ...t, ...patch } : t)) }));

  const buatCicilan = async () => {
    try {
      const res = await api.post("/payment-schemes/installments", {
        count: Number(gen.count) || 1, percent_total: Number(gen.percent) || 0,
        start_month: Number(gen.startMonth) || 1, due_day: Number(gen.dueDay) || 7,
        grace_days: Number(gen.grace) || 0 });
      setForm((f) => ({ ...f, terms: [...f.terms, ...(res.data.data || [])] }));
      setGen(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membuat cicilan.");
    }
  };

  const submit = async () => {
    try {
      const body = { name: form.name, kind: form.kind, active: form.active,
        is_default: form.is_default, note: form.note || null,
        applies_project_ids: form.applies_project_ids || [],
        terms: form.terms.map((t) => ({ ...t, value: Number(t.value) || 0 })) };
      if (form.id) await api.put(`/payment-schemes/${form.id}`, body);
      else await api.post("/payment-schemes", body);
      toast.success("Skema pembayaran disimpan.");
      setForm(null); setPreview(null); load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan skema.");
    }
  };

  if (state.loading) return <LoadingCards count={3} />;
  if (state.error) return <ErrorState message={state.error} onRetry={load} />;

  return (
    <div data-testid={P57.panel} className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="section-title">Skema pembayaran</h3>
          <p className="max-w-3xl text-xs text-muted-foreground">
            Susun termin sesuai kebiasaan bisnis Anda: DP nominal atau persen, jumlah
            cicilan, tanggal jatuh tempo, toleransi, dan termin yang menunggu peristiwa
            (pembangunan 100%, akad kredit). <strong>Jenis</strong> skema tetap menentukan
            tahap legal &amp; biaya yang berlaku — hanya jenis KPR yang punya akad kredit,
            biaya bank, dan asuransi.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ReferenceSelect group="payment_scheme_kind" value={kind} onChange={setKind}
            allowEmpty emptyLabel="Semua jenis" testId={P57.filterKind} className="w-[240px]" />
          <Button data-testid={P57.add} size="sm"
            onClick={() => { setForm({ ...KOSONG, terms: [{ ...TERM_BARU, label: "DP" }] }); }}>
            <Plus className="mr-1.5 h-3.5 w-3.5" /> Skema baru
          </Button>
        </div>
      </div>

      {rows.length ? (
        <div className="space-y-2">
          {rows.map((r) => (
            <div key={r.id} data-testid={P57.row}
              className="rounded-lg border bg-card p-3 text-sm shadow-[var(--shadow-card)]">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-medium">
                    {r.name}
                    {r.is_default ? (
                      <span className="ml-2 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] text-primary">
                        bawaan
                      </span>
                    ) : null}
                    {!r.active ? (
                      <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-[10px]">
                        nonaktif
                      </span>
                    ) : null}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {r.kind_label} · {(r.terms || []).length} termin ·{" "}
                    {(r.applies_project_ids || []).length
                      ? `${r.applies_project_ids.length} proyek tertentu`
                      : "semua proyek"}
                    {r.used_by_contracts
                      ? ` · dipakai ${r.used_by_contracts} kontrak` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button data-testid={P57.copy} size="sm" variant="ghost"
                    onClick={() => setForm({ ...KOSONG, kind: r.kind,
                      name: `${r.name} (salinan)`,
                      applies_project_ids: r.applies_project_ids || [],
                      terms: (r.terms || []).map((t) => ({ ...t })) })}>
                    <Copy className="mr-1.5 h-3.5 w-3.5" /> Salin
                  </Button>
                  <Button data-testid={P57.edit} size="sm" variant="outline"
                    onClick={() => setForm({ ...r, terms: (r.terms || []).map((t) => ({ ...t })) })}>
                    <Pencil className="mr-1.5 h-3.5 w-3.5" /> Ubah
                  </Button>
                </div>
              </div>
              <div className="mt-2 space-y-1">
                {(r.terms || []).map((t, i) => (
                  <p key={i} className="text-xs text-muted-foreground">
                    {i + 1}. <strong>{t.label}</strong> —{" "}
                    {t.basis === "percent" ? `${t.value}% dari harga`
                      : t.basis === "amount" ? formatIDR(t.value) : "sisa harga"}
                    {" · "}{t.due_rule}
                  </p>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState icon={CalendarClock} title="Belum ada skema pembayaran"
          description={state.reason
            || "Buat skema pertama Anda — termin yang disusun di sini dipakai kontrak untuk menagih."} />
      )}

      {/* ---------------------------------------------- editor + pratinjau ------------ */}
      <Dialog open={!!form} onOpenChange={(o) => { if (!o) { setForm(null); setPreview(null); } }}>
        <DialogContent data-testid={P57.dialog} className="max-h-[90vh] max-w-4xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{form?.id ? "Ubah skema pembayaran" : "Skema pembayaran baru"}</DialogTitle>
            <DialogDescription>
              Kalimat aturan jatuh tempo disusun sistem dari pilihan Anda — pembeli membaca
              kalimat itu di dokumen, jadi ia tidak boleh berbeda dari yang ditagihkan.
            </DialogDescription>
          </DialogHeader>

          {form ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <Label htmlFor="scheme-name">Nama skema</Label>
                  <Input id="scheme-name" data-testid={P57.formName} value={form.name}
                    placeholder="mis. Cash bertahap 12× (Cluster Utama)"
                    onChange={(e) => setForm({ ...form, name: e.target.value })} />
                </div>
                <div>
                  <Label>Jenis</Label>
                  <ReferenceSelect group="payment_scheme_kind" value={form.kind}
                    testId={P57.formKind}
                    onChange={(v) => setForm({ ...form, kind: v })} />
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-6">
                <div className="flex items-center gap-2">
                  <Switch data-testid={P57.formActive} checked={form.active}
                    onCheckedChange={(v) => setForm({ ...form, active: v })} />
                  <Label className="text-xs">Aktif (boleh dipakai kontrak baru)</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Switch data-testid={P57.formDefault} checked={form.is_default}
                    onCheckedChange={(v) => setForm({ ...form, is_default: v })} />
                  <Label className="text-xs">Jadikan skema bawaan organisasi</Label>
                </div>
              </div>

              {/* Berlaku di proyek mana. Kosong = SEMUA proyek — dikatakan apa adanya,
                  karena "kosong" di sini bukan berarti "belum diisi". */}
              <div data-testid={P57.formProjects} className="space-y-1">
                <Label className="text-xs">Berlaku pada proyek</Label>
                <div className="flex flex-wrap gap-3 rounded-md border p-2">
                  {projects.length ? projects.map((p) => {
                    const dipilih = (form.applies_project_ids || []).includes(p.id);
                    return (
                      <label key={p.id} className="flex items-center gap-1.5 text-xs">
                        <input type="checkbox" checked={dipilih}
                          onChange={() => setForm({ ...form,
                            applies_project_ids: dipilih
                              ? form.applies_project_ids.filter((x) => x !== p.id)
                              : [...(form.applies_project_ids || []), p.id] })} />
                        {p.name}
                      </label>
                    );
                  }) : <span className="text-xs text-muted-foreground">Belum ada proyek.</span>}
                </div>
                <p className="text-[11px] text-muted-foreground">
                  {(form.applies_project_ids || []).length
                    ? `Hanya ${form.applies_project_ids.length} proyek terpilih yang bisa memakai skema ini.`
                    : "Tidak ada yang dipilih = berlaku untuk SEMUA proyek."}
                </p>
              </div>

              {/* -------- termin -------- */}
              <div className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Label>Termin</Label>
                  <div className="flex gap-2">
                    <Button data-testid={P57.genOpen} type="button" size="sm" variant="secondary"
                      onClick={() => setGen({ count: 6, percent: 20, startMonth: 1, dueDay: 7, grace: 13 })}>
                      <Wand2 className="mr-1.5 h-3.5 w-3.5" /> Buat cicilan otomatis
                    </Button>
                    <Button data-testid={P57.termAdd} type="button" size="sm" variant="outline"
                      onClick={() => setForm({ ...form, terms: [...form.terms, { ...TERM_BARU }] })}>
                      <Plus className="mr-1.5 h-3.5 w-3.5" /> Tambah termin
                    </Button>
                  </div>
                </div>
                {form.terms.map((t, i) => (
                  <div key={i} data-testid={P57.termRow}
                    className="grid gap-2 rounded-lg border bg-background p-2 sm:grid-cols-12">
                    <Input className="sm:col-span-3" data-testid={P57.termLabel} value={t.label}
                      placeholder="Nama termin" onChange={(e) => ubahTerm(i, { label: e.target.value })} />
                    <div className="sm:col-span-3">
                      <ReferenceSelect group="term_basis" value={t.basis} testId={P57.termBasis}
                        onChange={(v) => ubahTerm(i, { basis: v })} />
                    </div>
                    {t.basis === "percent" || t.basis === "remaining" ? (
                      <Input className="sm:col-span-2" data-testid={P57.termValue} type="number"
                        value={t.basis === "remaining" ? "" : t.value}
                        disabled={t.basis === "remaining"}
                        placeholder="%"
                        onChange={(e) => ubahTerm(i, { value: e.target.value })} />
                    ) : (
                      <RupiahInput className="sm:col-span-2" data-testid={P57.termValue} value={t.value}
                        onChange={(e) => ubahTerm(i, { value: e.target.value })} />
                    )}
                    <div className="sm:col-span-3">
                      <ReferenceSelect group="term_due_mode" value={t.due_mode}
                        testId={P57.termDueMode}
                        onChange={(v) => ubahTerm(i, { due_mode: v })} />
                    </div>
                    <Button className="sm:col-span-1" data-testid={P57.termDelete} type="button"
                      size="sm" variant="ghost"
                      onClick={() => setForm({ ...form,
                        terms: form.terms.filter((_, idx) => idx !== i) })}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>

                    {t.due_mode === "monthly_day" ? (
                      <>
                        <Input className="sm:col-span-3" data-testid={P57.termDueDay} type="number"
                          value={t.due_day || ""} placeholder="Tanggal (1–28)"
                          onChange={(e) => ubahTerm(i, { due_day: e.target.value })} />
                        <Input className="sm:col-span-3" type="number"
                          value={t.month_index ?? ""} placeholder="Bulan ke-"
                          onChange={(e) => ubahTerm(i, { month_index: e.target.value })} />
                      </>
                    ) : null}
                    {t.due_mode === "offset_days" ? (
                      <Input className="sm:col-span-3" data-testid={P57.termOffset} type="number"
                        value={t.due_offset_days || 0} placeholder="Hari setelah aktif"
                        onChange={(e) => ubahTerm(i, { due_offset_days: e.target.value })} />
                    ) : null}
                    {t.due_mode === "event" ? (
                      <>
                        <div className="sm:col-span-4">
                          <ReferenceSelect group="term_due_event" value={t.event_code}
                            testId={P57.termEvent}
                            onChange={(v) => ubahTerm(i, { event_code: v })} />
                        </div>
                        <Input className="sm:col-span-2" type="number"
                          value={t.due_offset_days || 0} placeholder="maks hari"
                          onChange={(e) => ubahTerm(i, { due_offset_days: e.target.value })} />
                      </>
                    ) : null}
                    <Input className="sm:col-span-2" data-testid={P57.termGrace} type="number"
                      value={t.grace_days || 0} placeholder="Toleransi (hari)"
                      onChange={(e) => ubahTerm(i, { grace_days: e.target.value })} />
                    <p className="text-[11px] text-muted-foreground sm:col-span-12">
                      {t.due_rule || "Aturan jatuh tempo akan tampil di pratinjau."}
                    </p>
                  </div>
                ))}
              </div>

              {/* -------- pratinjau -------- */}
              <div className="space-y-2 rounded-lg border bg-secondary/30 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Label className="text-xs">Pratinjau atas harga jual</Label>
                  <RupiahInput data-testid={P57.previewPrice} className="w-[200px]"
                    value={price} onChange={(e) => setPrice(e.target.value)} />
                  <Button type="button" size="sm" variant="outline"
                    onClick={() => simulate(form.terms)}>Hitung ulang</Button>
                </div>
                {(preview?.blocks || []).length ? (
                  <ul data-testid={P57.previewBlocks}
                    className="space-y-1 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                    {preview.blocks.map((b) => <li key={b.code}>• {b.detail}</li>)}
                  </ul>
                ) : null}
                {(preview?.rows || []).map((r) => (
                  <div key={r.no} data-testid={P57.previewRow}
                    className="flex flex-wrap items-center justify-between gap-2 text-xs">
                    <span>
                      {r.no}. {r.label}{" "}
                      <span className="text-muted-foreground">
                        ({r.basis_label}) · {r.due_rule}
                        {r.event_based ? " · tanggal perkiraan" : ""}
                        {r.due_date ? ` · ${formatDateWIB(r.due_date)}` : ""}
                      </span>
                    </span>
                    <MoneyText value={r.amount} />
                  </div>
                ))}
                {preview ? (
                  <p data-testid={P57.previewTotal}
                    className={`text-xs font-medium ${preview.balanced ? "text-emerald-700" : "text-red-700"}`}>
                    {preview.rows?.length
                      ? `Total ditagihkan ${formatIDR(preview.total)} · `
                      : ""}
                    {preview.balanced ? "tepat sama dengan harga jual" : preview.note}
                    {preview.pending
                      ? ` · ${preview.pending} termin belum diberi nama, jadi belum dihitung`
                      : ""}
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}

          <DialogFooter>
            <Button variant="ghost" onClick={() => { setForm(null); setPreview(null); }}>
              Batal
            </Button>
            <Button data-testid={P57.submit} onClick={submit}
              disabled={!!(preview?.blocks || []).length}>
              Simpan skema
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* -------- pembantu cicilan -------- */}
      <Dialog open={!!gen} onOpenChange={(o) => { if (!o) setGen(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Buat cicilan otomatis</DialogTitle>
            <DialogDescription>
              Hasilnya menjadi baris termin biasa — masih bisa Anda ubah satu per satu.
              Sisa pembulatan dipikul cicilan terakhir supaya jumlah persen tetap tepat.
            </DialogDescription>
          </DialogHeader>
          {gen ? (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Jumlah cicilan</Label>
                <Input data-testid={P57.genCount} type="number" value={gen.count}
                  onChange={(e) => setGen({ ...gen, count: e.target.value })} />
              </div>
              <div>
                <Label className="text-xs">Total persen dibagi</Label>
                <Input data-testid={P57.genPercent} type="number" value={gen.percent}
                  onChange={(e) => setGen({ ...gen, percent: e.target.value })} />
              </div>
              <div>
                <Label className="text-xs">Mulai bulan ke-</Label>
                <Input type="number" value={gen.startMonth}
                  onChange={(e) => setGen({ ...gen, startMonth: e.target.value })} />
              </div>
              <div>
                <Label className="text-xs">Tanggal jatuh tempo</Label>
                <Input data-testid={P57.genDueDay} type="number" value={gen.dueDay}
                  onChange={(e) => setGen({ ...gen, dueDay: e.target.value })} />
              </div>
              <div>
                <Label className="text-xs">Toleransi (hari)</Label>
                <Input type="number" value={gen.grace}
                  onChange={(e) => setGen({ ...gen, grace: e.target.value })} />
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setGen(null)}>Batal</Button>
            <Button data-testid={P57.genSubmit} onClick={buatCicilan}>Tambahkan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
