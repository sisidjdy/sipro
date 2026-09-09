import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { PERMIT_COVERAGE } from "@/constants/testIds";

/** Kelola daftar jenis izin organisasi (setting `permit.types_custom`). */
export default function PermitTypesDialog({ open, onOpenChange }) {
  const { options, reload } = useReference();
  const [custom, setCustom] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  const builtin = options("permit_type")
    .filter((o) => !custom.includes(o.value));

  useEffect(() => {
    if (!open) return;
    setInput("");
    api.get("/settings/effective", { params: { keys: "permit.types_custom" } })
      .then((r) => setCustom(r.data.data?.["permit.types_custom"] || []))
      .catch(() => setCustom([]));
  }, [open]);

  const add = () => {
    const v = input.trim();
    if (!v) return;
    const taken = new Set([...custom, ...options("permit_type").map((o) => o.value)]
      .map((x) => String(x).toLowerCase()));
    if (taken.has(v.toLowerCase())) { toast.error("Jenis izin itu sudah ada di daftar."); return; }
    setCustom((prev) => [...prev, v]);
    setInput("");
  };

  const save = async () => {
    setBusy(true);
    try {
      await api.put("/settings/permit.types_custom", {
        value: custom, reason: "Kelola jenis izin dari panel perizinan",
      });
      toast.success("Daftar jenis izin disimpan.");
      reload();
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan jenis izin.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={PERMIT_COVERAGE.typesDialog} className="bg-card sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Kelola jenis izin</DialogTitle>
          <DialogDescription>
            Jenis tambahan berlaku untuk seluruh organisasi dan muncul di pemilih saat
            menambah izin. Menghapus jenis TIDAK mengubah izin yang sudah tercatat.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted-foreground">
              Jenis bawaan & yang sudah terpakai
            </p>
            <div className="flex flex-wrap gap-1">
              {builtin.map((o) => (
                <Badge key={o.value} variant="secondary" className="font-normal">{o.label}</Badge>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-1.5 text-xs font-medium text-muted-foreground">
              Jenis tambahan organisasi ini
            </p>
            {!custom.length ? (
              <p className="text-sm text-muted-foreground">Belum ada jenis tambahan.</p>
            ) : (
              <div className="flex flex-wrap gap-1">
                {custom.map((v) => (
                  <span key={v} data-testid="permit-types-custom-item" data-value={v}
                    className="inline-flex items-center gap-1 rounded-full border bg-secondary px-2 py-0.5 text-xs">
                    {v}
                    <button type="button" aria-label={`Hapus jenis ${v}`}
                      className="text-muted-foreground hover:text-destructive"
                      onClick={() => setCustom((prev) => prev.filter((x) => x !== v))}>
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="permit-type-new">Nama jenis izin baru</Label>
            <div className="flex gap-2">
              <Input id="permit-type-new" data-testid={PERMIT_COVERAGE.typesInput}
                value={input} onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
                placeholder="mis. IPPT, Izin Lingkungan RT/RW" />
              <Button type="button" variant="secondary" data-testid={PERMIT_COVERAGE.typesAdd}
                onClick={add} disabled={!input.trim()}>
                <Plus className="mr-1 h-3.5 w-3.5" /> Tambah
              </Button>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={PERMIT_COVERAGE.typesSave} onClick={save} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan daftar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
