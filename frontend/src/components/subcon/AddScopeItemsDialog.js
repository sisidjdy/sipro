import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2 } from "lucide-react";

import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Checkbox } from "@/components/ui/checkbox";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { formatIDR } from "@/utils/formatters";
import { SCOPE } from "@/constants/testIds";

const ALL = "__all__";

/**
 * Susun lingkup SPK dari ITEM JADWAL NYATA.
 *
 * Hanya pekerjaan yang belum dipakai SPK lain yang muncul (satu pekerjaan tidak boleh
 * dibayar lewat dua SPK). Harga awal diambil dari RAB sebagai ACUAN yang boleh diubah —
 * disebut apa adanya, bukan angka "pasti".
 */
export default function AddScopeItemsDialog({ spk, open, onOpenChange, onDone }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [unit, setUnit] = useState(ALL);
  const [picked, setPicked] = useState({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !spk?.id) return;
    setPicked({}); setUnit(ALL); setLoading(true);
    api.get(`/subcon/spk/${spk.id}/scope/candidates`)
      .then((r) => setData(r.data.data))
      .catch((e) => toast.error(e?.response?.data?.detail || "Gagal memuat kandidat pekerjaan."))
      .finally(() => setLoading(false));
  }, [open, spk?.id]);

  const units = data?.units || [];
  const shown = useMemo(
    () => (unit === ALL ? units : units.filter((u) => u.unit_id === unit)), [units, unit]);
  const total = useMemo(
    () => Object.values(picked).reduce((a, p) => a + (Number(p.value) || 0), 0), [picked]);
  const count = Object.keys(picked).length;
  const room = Number(data?.unallocated || 0);
  const over = room >= 0 && total > room;

  const toggle = (it) => setPicked((cur) => {
    const next = { ...cur };
    if (next[it.build_item_id]) delete next[it.build_item_id];
    else next[it.build_item_id] = { value: it.suggested_value || "", boq_item_id: it.boq_item_id };
    return next;
  });
  const setValue = (id, value) => setPicked((cur) => (
    cur[id] ? { ...cur, [id]: { ...cur[id], value } } : cur));

  const save = async () => {
    const lines = Object.entries(picked).map(([build_item_id, p]) => ({
      build_item_id, value: Number(p.value) || 0, boq_item_id: p.boq_item_id || undefined,
    }));
    if (!lines.length) { toast.error("Pilih minimal satu pekerjaan."); return; }
    if (lines.some((l) => l.value <= 0)) {
      toast.error("Isi nilai borongan setiap pekerjaan yang dipilih (lebih dari 0)."); return;
    }
    setBusy(true);
    try {
      await api.post(`/subcon/spk/${spk.id}/scope`, { lines });
      toast.success(`${lines.length} pekerjaan masuk lingkup SPK.`);
      onOpenChange(false); onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menambah lingkup.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={SCOPE.dialog} className="max-h-[88vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Tambah pekerjaan ke lingkup {spk?.spk_number}</DialogTitle>
          <DialogDescription>
            Pilih item jadwal unit yang diborongkan ke {spk?.subcontractor_name}. Nilai awal
            adalah harga acuan dari RAB dan boleh diubah. Pekerjaan baru bisa ditagih setelah
            diverifikasi supervisor.
          </DialogDescription>
        </DialogHeader>

        {loading ? <LoadingCards count={3} /> : !units.length ? (
          <EmptyState icon={CheckCircle2} title="Tidak ada pekerjaan yang tersedia"
            description={"Semua item jadwal proyek ini sudah masuk lingkup SPK lain, atau unit "
              + "belum punya jadwal pembangunan. Buat jadwal unit dulu di Progres & Mutu."} />
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Select value={unit} onValueChange={setUnit}>
                <SelectTrigger data-testid={SCOPE.unitFilter} className="w-[240px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>Semua unit ({units.length})</SelectItem>
                  {units.map((u) => (
                    <SelectItem key={u.unit_id} value={u.unit_id}>
                      {u.unit_code} ({u.items.length} pekerjaan)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[12px] text-muted-foreground">
                Sisa nilai kontrak belum diurai:{" "}
                <b className="tabular-nums">{formatIDR(room)}</b>
              </p>
            </div>

            <div className="max-h-[46vh] space-y-3 overflow-y-auto pr-1">
              {shown.map((u) => (
                <div key={u.unit_id} className="rounded-lg border">
                  <p className="border-b bg-secondary px-3 py-1.5 text-xs font-semibold">
                    Unit {u.unit_code}
                  </p>
                  <div className="divide-y">
                    {u.items.map((it) => {
                      const sel = picked[it.build_item_id];
                      return (
                        <div key={it.build_item_id} data-testid={SCOPE.candidate}
                          data-step={it.step_code}
                          className="flex flex-wrap items-center gap-2 px-3 py-2">
                          <Checkbox checked={!!sel} data-testid={SCOPE.candidateCheck}
                            aria-label={`Pilih ${it.step_code}`}
                            onCheckedChange={() => toggle(it)} />
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm">
                              <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px]">
                                {it.step_code}
                              </span>{" "}
                              {it.step_name}
                            </p>
                            <p className="text-[11px] text-muted-foreground">
                              minggu {it.week} · bobot {it.weight}%
                              {it.verified ? " · sudah terverifikasi" : " · belum terverifikasi"}
                              {it.cost_code ? ` · acuan RAB ${it.cost_code}` : " · belum ada acuan RAB"}
                            </p>
                          </div>
                          <RupiahInput className="w-[150px]" data-testid={SCOPE.valueInput}
                            aria-label={`Nilai borongan ${it.step_code}`}
                            placeholder={it.suggested_value ? String(it.suggested_value) : "Nilai (Rp)"}
                            value={sel?.value ?? ""} disabled={!sel}
                            onChange={(e) => setValue(it.build_item_id, e.target.value)} />
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            <div data-testid={SCOPE.dialogTotal}
              className={`rounded-lg p-3 text-sm ${over ? "bg-rose-50 text-rose-900" : "bg-secondary"}`}>
              {count} pekerjaan dipilih · total{" "}
              <b className="tabular-nums">{formatIDR(total)}</b>
              {over ? (
                <span className="block text-[12px]">
                  Melebihi sisa nilai kontrak ({formatIDR(room)}). Kurangi nilai, atau naikkan
                  nilai kontrak lewat Change Order.
                </span>
              ) : null}
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={SCOPE.save} disabled={busy || !count || over} onClick={save}>
            {busy ? "Menyimpan…" : "Masukkan ke lingkup"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
