import React, { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { COST } from "@/constants/testIds";

/**
 * PEMETAAN ITEM RAB → LANGKAH JADWAL (Fase 33).
 *
 * Gunanya dua: (1) memberi HARGA ACUAN saat menyusun lingkup borongan per pekerjaan,
 * (2) membuat kendali biaya bisa membandingkan anggaran dengan nilai yang dikontrakkan
 * pada pekerjaan yang sama. Nilai RAB dibagi RATA ke langkah yang dipilih — disebut apa
 * adanya supaya tidak terkesan presisi palsu.
 */
export default function BoQStepMapDialog({ projectId, item, open, onOpenChange, onDone }) {
  const [steps, setSteps] = useState(null);
  const [picked, setPicked] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !projectId) return;
    setPicked(item?.steps || []);
    setSteps(null);
    api.get("/boq/steps", { params: { project_id: projectId } })
      .then((r) => setSteps(r.data.data || []))
      .catch((e) => {
        setSteps([]);
        toast.error(e?.response?.data?.detail || "Gagal memuat langkah jadwal.");
      });
  }, [open, projectId, item]);

  const toggle = (code) => setPicked((cur) => (
    cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code]));

  const save = async () => {
    setBusy(true);
    try {
      await api.put(`/boq/items/${item.id}/steps`, { step_codes: picked });
      toast.success(picked.length
        ? `${item.code} dipetakan ke ${picked.length} langkah jadwal.`
        : `Pemetaan ${item.code} dihapus.`);
      onOpenChange(false); onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan pemetaan.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={COST.mapDialog} className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Petakan RAB {item?.code} ke langkah jadwal</DialogTitle>
          <DialogDescription>
            {item?.label} — nilai anggaran dibagi rata ke langkah yang dipilih, lalu dibagi
            jumlah unit yang memiliki langkah itu, sebagai harga acuan borongan.
          </DialogDescription>
        </DialogHeader>

        {steps === null ? <LoadingCards count={3} /> : !steps.length ? (
          <EmptyState title="Belum ada langkah jadwal"
            description="Proyek ini belum punya jadwal pembangunan unit, jadi belum ada langkah yang bisa dipetakan." />
        ) : (
          <div className="max-h-[50vh] divide-y overflow-y-auto rounded-lg border">
            {steps.map((s) => (
              <label key={s.step_code} data-testid={COST.mapStep}
                className="flex cursor-pointer items-center gap-3 p-2.5 hover:bg-secondary">
                <Checkbox checked={picked.includes(s.step_code)}
                  aria-label={`Petakan ke ${s.step_code}`}
                  onCheckedChange={() => toggle(s.step_code)} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">
                    <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px]">
                      {s.step_code}
                    </span>{" "}
                    {s.step_name}
                  </p>
                  <p className="text-[11px] text-muted-foreground">
                    minggu {s.week} · {s.units} unit · bobot {s.weight}%
                  </p>
                </div>
              </label>
            ))}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Batal</Button>
          <Button data-testid={COST.mapSave} disabled={busy || !steps?.length} onClick={save}>
            {busy ? "Menyimpan…" : "Simpan pemetaan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
