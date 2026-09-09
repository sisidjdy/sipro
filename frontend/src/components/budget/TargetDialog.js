import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Eye, Save } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { Count, MissingNote, Money } from "@/components/budget/parts";
import api from "@/services/apiClient";
import { BUDGET } from "@/constants/testIds";

/**
 * TargetDialog — buat / ubah target proyek dengan **PRATINJAU DAMPAK sebelum disimpan**
 * (Definition of Done #1, `docs/v2/32` §6).
 *
 * Kenapa pratinjau wajib ada: mengubah metode target mengubah rencana SELURUH bulan
 * berikutnya. Kalau pemakai harus menyimpan dulu untuk melihat akibatnya, ia sudah mengubah
 * rencana resmi perusahaan sebelum tahu hasilnya — dan rencana lama sudah hilang.
 *
 * Pratinjau memakai endpoint yang SAMA dengan penyimpanan (`POST /api/targets/preview` →
 * mesin `target_engine`), bukan hitungan tiruan di layar. Rumus yang ditampilkan juga datang
 * dari backend, jadi penjelasan di layar tidak bisa berbeda dengan yang dijalankan mesin.
 */
const EMPTY = {
  name: "", method: "linear_remaining", basis: "both", scope: "project",
  start: "", end: "", unit_target: "0", revenue_target: "0", avg_price: "0",
  growth_pct: "0", owner_email: "", cluster_id: "",
};

/** Nilai awal field angka: kosong bila belum ada nilai (BUKAN "0" yang tampak sengaja diisi). */
const numStr = (v) => (v === null || v === undefined ? "" : String(v));

function monthList(start, end) {
  if (!start || !end) return [];
  const out = [];
  let [y, m] = start.split("-").map(Number);
  const [ey, em] = end.split("-").map(Number);
  let guard = 0;
  while ((y < ey || (y === ey && m <= em)) && guard < 120) {
    out.push(`${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}`);
    m += 1;
    if (m > 12) { m = 1; y += 1; }
    guard += 1;
  }
  return out;
}

export default function TargetDialog({ projectId, target, open, onOpenChange, onDone }) {
  const [form, setForm] = useState(EMPTY);
  const [weights, setWeights] = useState({});
  const [manual, setManual] = useState({});
  const [methods, setMethods] = useState([]);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => { setForm((f) => ({ ...f, [k]: v })); setPreview(null); };
  const editing = !!target;

  useEffect(() => {
    if (!open) return;
    setPreview(null);
    if (target) {
      setForm({
        name: target.name || "", method: target.method || "linear_remaining",
        basis: target.basis || "both", scope: target.scope || "project",
        start: target.horizon?.start || "", end: target.horizon?.end || "",
        unit_target: numStr(target.unit_target),
        revenue_target: numStr(target.revenue_target),
        avg_price: numStr(target.assumptions?.avg_price),
        growth_pct: numStr(target.assumptions?.growth_pct),
        owner_email: target.owner_email || "", cluster_id: target.cluster_id || "",
      });
      setWeights(target.weights || {});
      setManual(target.manual_plan || {});
    } else {
      const year = new Date().getFullYear();
      setForm({ ...EMPTY, name: `Target ${year}`, start: `${year}-01`, end: `${year}-12` });
      setWeights({}); setManual({});
    }
  }, [open, target]);

  useEffect(() => {
    if (!open) return;
    api.get("/targets/methods").then((r) => setMethods(r.data.data || [])).catch(() => {});
  }, [open]);

  const months = useMemo(() => monthList(form.start, form.end), [form.start, form.end]);
  const methodMeta = methods.find((m) => m.value === form.method);

  const payload = useCallback(() => ({
    project_id: projectId,
    name: form.name.trim(), method: form.method, basis: form.basis, scope: form.scope,
    cluster_id: form.scope === "cluster" ? (form.cluster_id || null) : null,
    owner_email: form.scope === "sales" ? (form.owner_email.trim() || null) : null,
    horizon: { start: form.start, end: form.end },
    unit_target: Math.round(Number(form.unit_target) || 0),
    revenue_target: Math.round(Number(form.revenue_target) || 0),
    weights: form.method === "s_curve" ? weights : {},
    manual_plan: form.method === "manual" ? manual : {},
    assumptions: {
      avg_price: Math.round(Number(form.avg_price) || 0), opex_monthly: 0,
      growth_pct: Number(form.growth_pct) || 0,
    },
  }), [projectId, form, weights, manual]);

  const doPreview = async () => {
    if (!form.start || !form.end) { toast.error("Isi bulan mulai & selesai dulu."); return; }
    setBusy(true);
    try {
      const body = { ...payload() };
      if (editing) body.target_id = target.id;
      const r = await api.post("/targets/preview", body);
      setPreview(r.data.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membuat pratinjau.");
    } finally { setBusy(false); }
  };

  const submit = async () => {
    if (form.name.trim().length < 3) { toast.error("Nama target minimal 3 huruf."); return; }
    if (!form.start || !form.end) { toast.error("Isi bulan mulai & selesai."); return; }
    setBusy(true);
    try {
      if (editing) {
        const body = { ...payload() };
        delete body.project_id; delete body.scope;
        delete body.cluster_id; delete body.owner_email;
        body.reason = "Target diubah dari layar Target & Budget";
        await api.put(`/targets/${target.id}`, body);
        toast.success("Target diperbarui & periodenya dihitung ulang.");
      } else {
        await api.post("/targets", payload());
        toast.success("Target dibuat sebagai draf — aktifkan bila sudah benar.");
      }
      onOpenChange(false); onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan target.");
    } finally { setBusy(false); }
  };

  const after = preview?.after;
  const beforeMap = {};
  (preview?.before?.periods || []).forEach((p) => { beforeMap[p.period] = p; });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={BUDGET.targetDialog}
        className="max-h-[88vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{editing ? "Ubah Target Proyek" : "Buat Target Proyek"}</DialogTitle>
          <DialogDescription>
            Realisasi target TIDAK diinput di sini — unit terjual & nilainya dibaca dari deal
            yang benar-benar tercatat. Lihat dampaknya dulu sebelum menyimpan.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="target-name">Nama target</Label>
            <Input id="target-name" data-testid={BUDGET.targetName} value={form.name}
              onChange={(e) => set("name", e.target.value)} placeholder="mis. Target 2026" />
          </div>
          <div className="space-y-1.5">
            <Label>Metode perhitungan</Label>
            <ReferenceSelect group="target_method" value={form.method}
              onChange={(v) => set("method", v)} testId={BUDGET.targetMethod} />
          </div>
          <div className="space-y-1.5">
            <Label>Basis target</Label>
            <ReferenceSelect group="target_basis" value={form.basis}
              onChange={(v) => set("basis", v)} testId={BUDGET.targetBasis} />
          </div>
          {!editing ? (
            <div className="space-y-1.5">
              <Label>Cakupan</Label>
              <ReferenceSelect group="target_scope" value={form.scope}
                onChange={(v) => set("scope", v)} testId={BUDGET.targetScope} />
            </div>
          ) : null}
          {!editing && form.scope === "sales" ? (
            <div className="space-y-1.5">
              <Label htmlFor="target-owner">Email sales pemilik target</Label>
              <Input id="target-owner" type="email" value={form.owner_email}
                onChange={(e) => set("owner_email", e.target.value)}
                placeholder="sales@sipro.co.id" />
            </div>
          ) : null}
          {!editing && form.scope === "cluster" ? (
            <div className="space-y-1.5">
              <Label htmlFor="target-cluster">Kode/ID cluster</Label>
              <Input id="target-cluster" value={form.cluster_id}
                onChange={(e) => set("cluster_id", e.target.value)}
                placeholder="id cluster" />
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label htmlFor="target-start">Bulan mulai</Label>
            <Input id="target-start" type="month" data-testid={BUDGET.targetStart}
              value={form.start} onChange={(e) => set("start", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="target-end">Bulan selesai</Label>
            <Input id="target-end" type="month" data-testid={BUDGET.targetEnd}
              value={form.end} onChange={(e) => set("end", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="target-unit">Total target unit terjual</Label>
            <Input id="target-unit" type="number" min="0" data-testid={BUDGET.targetUnit}
              value={form.unit_target} onChange={(e) => set("unit_target", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="target-revenue">Total target pendapatan (Rp)</Label>
            <RupiahInput id="target-revenue" data-testid={BUDGET.targetRevenue}
              value={form.revenue_target}
              onChange={(e) => set("revenue_target", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="target-avgprice">Harga rata-rata unit (Rp)</Label>            <RupiahInput id="target-avgprice" data-testid={BUDGET.targetAvgPrice}
              value={form.avg_price} onChange={(e) => set("avg_price", e.target.value)} />
            <p className="text-[11px] text-muted-foreground">
              Kosongkan (0) untuk memakai rata-rata harga unit proyek yang benar-benar berharga.
            </p>
          </div>
          {form.method === "velocity_forecast" ? (
            <div className="space-y-1.5">
              <Label htmlFor="target-growth">Asumsi pertumbuhan (persen)</Label>
              <Input id="target-growth" type="number" data-testid={BUDGET.targetGrowth}
                value={form.growth_pct} onChange={(e) => set("growth_pct", e.target.value)} />
            </div>
          ) : null}
        </div>

        {methodMeta ? (
          <div data-testid={BUDGET.targetFormula}
            className="rounded-lg border bg-secondary/40 p-3 text-[12px]">
            <p className="font-medium">Rumus yang dijalankan mesin</p>
            <p className="mt-0.5 font-mono text-[11px]">{methodMeta.formula}</p>
            {(methodMeta.needs || []).length ? (
              <p className="mt-1 text-muted-foreground">
                Membutuhkan: {methodMeta.needs.join(" · ")}
              </p>
            ) : null}
          </div>
        ) : null}

        {form.method === "s_curve" && months.length ? (
          <div className="space-y-2">
            <Label>Bobot kurva-S per bulan (persen, idealnya total 100)</Label>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
              {months.map((m) => (
                <div key={m} className="space-y-1">
                  <Label htmlFor={`w-${m}`} className="text-[10px] text-muted-foreground">{m}</Label>
                  <Input id={`w-${m}`} type="number" min="0" className="h-8 text-xs"
                    aria-label={`Bobot kurva-S bulan ${m} (persen)`}
                    data-testid={`${BUDGET.targetWeight}-${m}`}
                    value={weights[m] ?? ""}
                    onChange={(e) => {
                      setWeights((w) => ({ ...w, [m]: Number(e.target.value) || 0 }));
                      setPreview(null);
                    }} />
                </div>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">
              Total bobot saat ini:{" "}
              {Object.values(weights).reduce((a, b) => a + (Number(b) || 0), 0)}%
            </p>
          </div>
        ) : null}

        {form.method === "manual" && months.length ? (
          <div className="space-y-2">
            <Label>Rencana unit per bulan (diisi manual)</Label>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
              {months.map((m) => (
                <div key={m} className="space-y-1">
                  <Label htmlFor={`mp-${m}`} className="text-[10px] text-muted-foreground">{m}</Label>
                  <Input id={`mp-${m}`} type="number" min="0" className="h-8 text-xs"
                    aria-label={`Rencana unit bulan ${m}`}
                    data-testid={`${BUDGET.targetManual}-${m}`}
                    value={manual[m] ?? ""}
                    onChange={(e) => {
                      setManual((x) => ({ ...x, [m]: Number(e.target.value) || 0 }));
                      setPreview(null);
                    }} />
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {preview ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="font-semibold">Dampak perubahan</span>
              <span className="text-muted-foreground">
                {preview.changes.length} bulan berubah · metode {preview.method_before || "-"}
                {" → "}{preview.method_after}
              </span>
            </div>
            <MissingNote items={after?.missing}
              title="Rencana belum bisa dihitung karena:" />
            {(after?.warnings || []).map((w, i) => (
              <p key={i}
                className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-[12px] text-amber-900">
                {w}
              </p>
            ))}
            <div data-testid={BUDGET.targetPreviewTable}
              className="max-h-64 overflow-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Bulan</TableHead>
                  <TableHead className="text-right">Rencana lama</TableHead>
                  <TableHead className="text-right">Rencana baru</TableHead>
                  <TableHead className="text-right">Realisasi</TableHead>
                  <TableHead className="text-right">Rencana pendapatan</TableHead>
                  <TableHead>Catatan</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {(after?.periods || []).map((p) => (
                    <TableRow key={p.period} data-testid={BUDGET.targetPreviewRow}
                      data-locked={p.locked ? "true" : "false"}>
                      <TableCell className="font-mono text-xs">{p.period}</TableCell>
                      <TableCell className="text-right text-xs">
                        <Count value={beforeMap[p.period]?.unit_plan} />
                      </TableCell>
                      <TableCell className="text-right text-xs font-medium">
                        <Count value={p.unit_plan} />
                      </TableCell>
                      <TableCell className="text-right text-xs">
                        <Count value={p.unit_actual} />
                      </TableCell>
                      <TableCell className="text-right text-xs">
                        <Money value={p.revenue_plan} />
                      </TableCell>
                      <TableCell className="text-[11px] text-muted-foreground">
                        {p.note || (p.locked ? "dikunci" : "")}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <p className="text-[11px] text-muted-foreground">
              {after?.totals?.keep_total_ok === true
                ? `Σ rencana ke depan + realisasi lampau = ${after.totals.unit_plan_future
                  + after.totals.unit_actual_past} unit, sama dengan total target `
                  + `${after.totals.unit_target} unit.`
                : "Σ rencana belum bisa dijumlahkan karena rencananya belum bisa dihitung."}
            </p>
          </div>
        ) : null}

        <DialogFooter className="gap-2">
          <Button type="button" variant="secondary" disabled={busy}
            data-testid={BUDGET.targetPreviewBtn} onClick={doPreview}>
            <Eye className="mr-1.5 h-4 w-4" /> Lihat dampak dulu
          </Button>
          <Button type="button" disabled={busy} data-testid={BUDGET.targetSave} onClick={submit}>
            <Save className="mr-1.5 h-4 w-4" /> {editing ? "Simpan perubahan" : "Simpan draf"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
