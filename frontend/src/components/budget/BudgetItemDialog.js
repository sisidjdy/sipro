import React, { useEffect, useMemo, useState } from "react";
import { Save } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import { useReference } from "@/context/ReferenceContext";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { BUDGET } from "@/constants/testIds";

/**
 * BudgetItemDialog — tambah/ubah item master anggaran (keputusan D6: bisa ditambah user).
 *
 * Satu aturan yang dipaksakan di sini DAN di server: item kategori **konstruksi** dengan
 * aturan “dari item RAB” TIDAK punya kolom rencana yang bisa diisi — rencananya dihitung dari
 * Σ item RAB yang ditaut. Kalau kolomnya dibiarkan bisa diisi, akan ada dua angka anggaran
 * konstruksi (satu di RAB, satu di sini) dan laporan overbudget kehilangan artinya.
 */
const EMPTY = {
  code: "", name: "", category: "operasional", match_rule: "by_gl_account",
  planned_amount: "0", gl_account: "", owner_role: "project_manager", period: "project",
  description: "", boq_item_ids: [],
};

export default function BudgetItemDialog({ projectId, item, open, onOpenChange, onDone }) {
  const { labelOf } = useReference();
  const [form, setForm] = useState(EMPTY);
  const [boq, setBoq] = useState([]);
  const [busy, setBusy] = useState(false);
  const editing = !!item;
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (!open) return;
    if (item) {
      setForm({
        code: item.code || "", name: item.name || "", category: item.category || "operasional",
        match_rule: item.match_rule || "manual",
        planned_amount: item.planned_amount === null
          || item.planned_amount === undefined ? "" : String(item.planned_amount),
        gl_account: item.gl_account || "", owner_role: item.owner_role || "project_manager",
        period: item.period || "project", description: item.description || "",
        boq_item_ids: item.boq_item_ids || [],
      });
    } else setForm(EMPTY);
  }, [open, item]);

  useEffect(() => {
    if (!open || !projectId) return;
    api.get("/boq/items", { params: { project_id: projectId } })
      .then((r) => setBoq(r.data.data || [])).catch(() => setBoq([]));
  }, [open, projectId]);

  const readonlyPlan = form.category === "konstruksi" && form.match_rule === "by_boq_item";
  const boqTotal = useMemo(
    () => boq.filter((b) => form.boq_item_ids.includes(b.id))
      .reduce((a, b) => a + (b.amount || 0), 0),
    [boq, form.boq_item_ids]);

  const toggleBoq = (id) => setForm((f) => ({
    ...f,
    boq_item_ids: f.boq_item_ids.includes(id)
      ? f.boq_item_ids.filter((x) => x !== id) : [...f.boq_item_ids, id],
  }));

  const submit = async () => {
    if (!editing && form.code.trim().length < 2) { toast.error("Isi kode anggaran."); return; }
    if (form.name.trim().length < 3) { toast.error("Isi nama item anggaran."); return; }
    setBusy(true);
    try {
      const body = {
        category: form.category, name: form.name.trim(),
        description: form.description.trim() || null,
        match_rule: form.match_rule,
        gl_account: form.match_rule === "by_gl_account" ? (form.gl_account || null) : null,
        boq_item_ids: form.match_rule === "by_boq_item" ? form.boq_item_ids : [],
        owner_role: form.owner_role || null, period: form.period,
      };
      if (editing) {
        await api.put(`/budget/items/${item.id}`, body);
        toast.success("Item anggaran diperbarui.");
      } else {
        await api.post("/budget/items", {
          ...body, project_id: projectId, code: form.code.trim().toUpperCase(),
          planned_amount: readonlyPlan ? 0 : Math.round(Number(form.planned_amount) || 0),
        });
        toast.success("Item anggaran ditambahkan.");
      }
      onOpenChange(false); onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan item anggaran.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={BUDGET.itemDialog}
        className="max-h-[88vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{editing ? "Ubah Item Anggaran" : "Tambah Item Anggaran"}</DialogTitle>
          <DialogDescription>
            Setiap item wajib menyatakan DARI MANA realisasinya diambil — supaya tidak ada
            angka realisasi tanpa asal.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 sm:grid-cols-2">
          {!editing ? (
            <div className="space-y-1.5">
              <Label htmlFor="bi-code">Kode anggaran</Label>
              <Input id="bi-code" data-testid={BUDGET.itemCode} value={form.code}
                onChange={(e) => set("code", e.target.value)} placeholder="mis. OPS-GAJI" />
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label htmlFor="bi-name">Nama item</Label>
            <Input id="bi-name" data-testid={BUDGET.itemName} value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="mis. Gaji tim proyek" />
          </div>
          <div className="space-y-1.5">
            <Label>Kategori anggaran</Label>
            <ReferenceSelect group="budget_category" value={form.category}
              onChange={(v) => set("category", v)} testId={BUDGET.itemCategory} />
          </div>
          <div className="space-y-1.5">
            <Label>Cara mencocokkan realisasi</Label>
            <ReferenceSelect group="budget_match_rule" value={form.match_rule}
              onChange={(v) => set("match_rule", v)} testId={BUDGET.itemRule} />
          </div>
          {form.match_rule === "by_gl_account" ? (
            <div className="space-y-1.5">
              <Label>Akun buku besar</Label>
              <ReferenceSelect group="gl_account" value={form.gl_account}
                onChange={(v) => set("gl_account", v)} testId={BUDGET.itemGl}
                placeholder="Pilih akun beban…" />
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label>Peran penanggung jawab</Label>
            <ReferenceSelect group="user_role" value={form.owner_role}
              onChange={(v) => set("owner_role", v)} testId={BUDGET.itemOwner} />
          </div>
          <div className="space-y-1.5">
            <Label>Periode anggaran</Label>
            <ReferenceSelect group="budget_period" value={form.period}
              onChange={(v) => set("period", v)} testId={BUDGET.itemPeriod} />
          </div>
          {!editing ? (
            <div className="space-y-1.5">
              <Label htmlFor="bi-planned">Rencana anggaran (Rp)</Label>
              <RupiahInput id="bi-planned" data-testid={BUDGET.itemPlanned}
                disabled={readonlyPlan} value={readonlyPlan ? "" : form.planned_amount}
                onChange={(e) => set("planned_amount", e.target.value)}
                placeholder={readonlyPlan ? "dihitung dari item RAB" : "0"} />
              {readonlyPlan ? (
                <p data-testid={BUDGET.itemReadonlyHint} className="text-[11px] text-amber-700">
                  Rencana item konstruksi dihitung dari Σ item RAB yang ditaut ({formatIDR(boqTotal)})
                  — tidak bisa diisi tangan supaya tidak ada dua angka anggaran konstruksi.
                </p>
              ) : null}
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label>Rencana anggaran</Label>
              <p className="rounded-md border bg-secondary/40 px-3 py-2 text-sm tabular-nums">
                {formatIDR(item.planned_amount)}
              </p>
              <p className="text-[11px] text-muted-foreground">
                Mengubah rencana dilakukan lewat tombol “Revisi” (wajib beralasan &amp; butuh
                persetujuan) — bukan diam-diam lewat form ini.
              </p>
            </div>
          )}
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="bi-desc">Keterangan</Label>
            <Textarea id="bi-desc" rows={2} value={form.description}
              onChange={(e) => set("description", e.target.value)}
              placeholder="Penjelasan singkat isi pos biaya ini" />
          </div>
        </div>

        {form.match_rule === "by_boq_item" ? (
          <div className="space-y-2">
            <Label>Item RAB yang diringkas</Label>
            {!boq.length ? (
              <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-[12px] text-amber-900">
                Proyek ini belum punya item RAB. Susun RAB di tab “Rincian RAB” lebih dulu.
              </p>
            ) : (
              <div data-testid={BUDGET.itemBoq}
                className="max-h-52 space-y-1 overflow-y-auto rounded-xl border bg-card p-2 shadow-[var(--shadow-card)]">
                {boq.map((b) => (
                  <label key={b.id} data-testid={BUDGET.itemBoqOption}
                    className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-xs hover:bg-secondary">
                    <input type="checkbox" checked={form.boq_item_ids.includes(b.id)}
                      onChange={() => toggleBoq(b.id)}
                      aria-label={`Taut item RAB ${b.cost_code || b.description}`} />
                    <span className="font-mono">{b.cost_code || "-"}</span>
                    <span className="flex-1 truncate">{b.description}</span>
                    <span className="text-[11px] text-muted-foreground">
                      {labelOf("work_category", b.category)}
                    </span>
                    <span className="tabular-nums">{formatIDR(b.amount)}</span>
                  </label>
                ))}
              </div>
            )}
            <p className="text-[11px] text-muted-foreground">
              Total item RAB terpilih: <span className="font-medium">{formatIDR(boqTotal)}</span>
              {" "}— inilah rencana anggaran item ini.
            </p>
          </div>
        ) : null}

        <DialogFooter>
          <Button type="button" disabled={busy} data-testid={BUDGET.itemSave} onClick={submit}>
            <Save className="mr-1.5 h-4 w-4" /> Simpan
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
