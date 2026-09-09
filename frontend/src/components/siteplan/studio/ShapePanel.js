import React, { useEffect, useState } from "react";
import { Link2Off, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { STUDIO } from "@/constants/testIds";

const KIND_TEXT = { lot: "Kavling", road: "Jalan", green: "Taman", water: "Air/Danau", facility: "Fasilitas", boundary: "Batas lahan" };

/** Panel bentuk terpilih: label, jenis, pemetaan ke unit, hapus. */
export default function ShapePanel({ s }) {
  const sh = s.selected;
  const [label, setLabel] = useState("");
  useEffect(() => { setLabel(sh?.label || ""); }, [sh?.shape_id, sh?.label]);
  if (!sh) {
    return (
      <p data-testid={STUDIO.emptyHint} className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
        Klik sebuah bentuk di kanvas untuk melihat detail & memetakannya ke unit. Kavling
        <span className="mx-1 inline-block h-2.5 w-2.5 rounded-sm border border-amber-500 bg-orange-50 align-middle" /> belum terpetakan,
        <span className="mx-1 inline-block h-2.5 w-2.5 rounded-sm border border-green-700 bg-green-200 align-middle" /> sudah.
      </p>
    );
  }
  const unit = s.unitsById[sh.unit_id];
  const choices = unit ? [unit, ...s.unmappedUnits] : s.unmappedUnits;
  return (
    <div className="space-y-3">
      <div className="rounded-lg border bg-muted/30 p-3">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Bentuk</p>
        <p className="font-mono text-xs">{sh.shape_id}</p>
        {sh.manual ? <p className="text-[11px] text-sky-700">digambar manual</p> : null}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="shape-label">Label di gambar</Label>
        <div className="flex gap-2">
          <Input id="shape-label" data-testid={STUDIO.shapeLabel} value={label} placeholder="mis. A-01"
            onChange={(e) => setLabel(e.target.value)} />
          <Button size="sm" data-testid={STUDIO.shapeSave} disabled={label === (sh.label || "") || !!s.busy}
            onClick={() => s.patchShape(sh.shape_id, { label })}>Simpan</Button>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label>Jenis bentuk</Label>
        <Select value={sh.kind} onValueChange={(v) => s.patchShape(sh.shape_id, { kind: v })}>
          <SelectTrigger data-testid={STUDIO.shapeKind} aria-label="Jenis bentuk"><SelectValue /></SelectTrigger>
          <SelectContent>{Object.entries(KIND_TEXT).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      {sh.kind === "lot" ? (
        <div className="space-y-1.5">
          <Label>Unit di database</Label>
          <Select value={sh.unit_id || ""} onValueChange={(v) => s.assignUnit(sh.shape_id, v)}>
            <SelectTrigger data-testid={STUDIO.shapeUnit} aria-label="Unit"><SelectValue placeholder="Pilih unit…" /></SelectTrigger>
            <SelectContent className="max-h-72">
              {choices.map((u) => <SelectItem key={u.id} value={u.id}>{u.code}{u.type ? ` · ${u.type}` : ""}</SelectItem>)}
            </SelectContent>
          </Select>
          {unit ? (
            <Button size="sm" variant="ghost" data-testid={STUDIO.shapeUnmap} onClick={() => s.assignUnit(sh.shape_id, "")}>
              <Link2Off className="mr-1.5 h-3.5 w-3.5" /> Lepas pemetaan
            </Button>
          ) : (
            <p className="text-xs text-amber-700">
              Belum ada unit untuk kavling ini. Pilih unit yang ada, atau buat unitnya lewat tab <strong>Buat unit</strong>.
            </p>
          )}
        </div>
      ) : null}
      <Button size="sm" variant="outline" className="text-destructive" data-testid={STUDIO.shapeDelete}
        onClick={() => s.deleteShape(sh.shape_id)}>
        <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Hapus bentuk dari peta
      </Button>
    </div>
  );
}
