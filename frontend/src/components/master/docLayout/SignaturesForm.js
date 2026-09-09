import React from "react";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ImageField } from "@/components/master/docLayout/BrandForm";
import { P60 } from "@/constants/testIds";

/**
 * SignaturesForm — kolom tanda tangan, materai, tempat & tanggal.
 *
 * Dokumen lama hanya punya dua kotak kosong bertuliskan peran. Sekarang: jumlah kolom
 * (maks 4), judul peran, nama & jabatan, spesimen tanda tangan/cap perusahaan, dan opsi
 * "ambil nama dari penerbit dokumen" — supaya dokumen tidak pernah keluar dengan nama
 * penandatangan yang salah karena lupa diubah.
 */
export default function SignaturesForm({ signatures, options, setSignatures, setOptions }) {
  const patch = (i, key, val) => setSignatures(signatures.map((s, idx) =>
    (idx === i ? { ...s, [key]: val } : s)));
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <label data-testid={P60.materai} className="flex items-center gap-2 text-[12px]">
          <input type="checkbox" checked={options.show_materai !== false}
            onChange={(e) => setOptions("show_materai", e.target.checked)} />
          Cetak keterangan meterai
        </label>
        <label data-testid={P60.placeDate} className="flex items-center gap-2 text-[12px]">
          <input type="checkbox" checked={options.show_place_date !== false}
            onChange={(e) => setOptions("show_place_date", e.target.checked)} />
          Cetak tempat &amp; tanggal
        </label>
        <div>
          <Label htmlFor="dl-place" className="text-[11px]">Kota penandatanganan</Label>
          <Input id="dl-place" data-testid={P60.place} className="h-8 w-[180px] bg-background"
            placeholder="mis. Bandung" value={options.place || ""}
            onChange={(e) => setOptions("place", e.target.value)} />
        </div>
      </div>

      {signatures.map((s, i) => (
        <div key={`sig-${i}`} data-testid={P60.signItem}
          className="space-y-2 rounded-lg border bg-card p-2.5 shadow-[var(--shadow-card)]">
          <div className="grid gap-2 sm:grid-cols-3">
            <div>
              <Label htmlFor={`dl-st-${i}`} className="text-[11px]">Judul kolom / peran</Label>
              <Input id={`dl-st-${i}`} data-testid={P60.signTitle} className="h-8 bg-background"
                value={s.title || ""} onChange={(e) => patch(i, "title", e.target.value)} />
            </div>
            <div>
              <Label htmlFor={`dl-sn-${i}`} className="text-[11px]">Nama penanda tangan</Label>
              <Input id={`dl-sn-${i}`} data-testid={P60.signName} className="h-8 bg-background"
                value={s.name || ""} disabled={!!s.auto_from_issuer}
                onChange={(e) => patch(i, "name", e.target.value)} />
            </div>
            <div>
              <Label htmlFor={`dl-sp-${i}`} className="text-[11px]">Jabatan</Label>
              <Input id={`dl-sp-${i}`} data-testid={P60.signPosition} className="h-8 bg-background"
                value={s.position || ""}
                onChange={(e) => patch(i, "position", e.target.value)} />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label data-testid={P60.signStamp} className="flex items-center gap-1.5 text-[12px]">
              <input type="checkbox" checked={!!s.show_stamp}
                onChange={(e) => patch(i, "show_stamp", e.target.checked)} />
              Cap perusahaan / meterai di kolom ini
            </label>
            <label data-testid={P60.signAuto} className="flex items-center gap-1.5 text-[12px]">
              <input type="checkbox" checked={!!s.auto_from_issuer}
                onChange={(e) => patch(i, "auto_from_issuer", e.target.checked)} />
              Ambil nama dari penerbit dokumen
            </label>
            {signatures.length > 1 ? (
              <Button size="sm" variant="ghost" data-testid={P60.signRemove}
                className="ml-auto" onClick={() => setSignatures(
                  signatures.filter((_x, idx) => idx !== i))}>
                <Trash2 className="mr-1 h-3.5 w-3.5" /> Hapus kolom
              </Button>
            ) : null}
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <ImageField label="Spesimen tanda tangan" testId={P60.signUpload}
              value={s.sign_file_id} hint="opsional (PNG transparan)"
              onChange={(v) => patch(i, "sign_file_id", v)} />
            <ImageField label="Cap / stempel" testId="doc-layout-stamp-upload"
              value={s.stamp_file_id} hint="opsional"
              onChange={(v) => patch(i, "stamp_file_id", v)} />
          </div>
        </div>
      ))}

      {signatures.length < 4 ? (
        <Button size="sm" variant="outline" data-testid={P60.signAdd}
          onClick={() => setSignatures([...signatures, {
            title: "Menyaksikan", name: "", position: "", show_stamp: false,
            auto_from_issuer: false,
          }])}>
          <Plus className="mr-1 h-3.5 w-3.5" /> Tambah kolom tanda tangan
        </Button>
      ) : (
        <p className="text-[11px] text-muted-foreground">
          Maksimal 4 kolom — lebih dari itu tidak lagi terbaca pada kertas A4.
        </p>
      )}
    </div>
  );
}
