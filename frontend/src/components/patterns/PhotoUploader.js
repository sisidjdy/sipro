import React, { useRef, useState } from "react";
import { Camera, ImagePlus, Loader2, MapPin, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import api from "@/services/apiClient";
import * as sync from "@/services/offlineSync";
import { photoSrc } from "@/utils/photoSrc";
import { BUILD, FIELD, OFFLINE } from "@/constants/testIds";

const MAX_MB = 8;

/**
 * PhotoUploader — unggah foto lapangan ke OBJECT STORAGE NYATA lalu simpan `file_id`.
 *
 * Sebelum Fase 28b foto disimpan sebagai data URL base64 di dalam dokumen Mongo:
 * satu foto ~1,5 MB membuat dokumen (dan setiap response yang memuatnya) membengkak,
 * tidak bisa di-cache browser, dan hanya boleh satu foto per catatan. Sekarang berkas
 * diunggah lewat `POST /files/upload`, dokumen hanya menyimpan daftar id, dan gambar
 * dilayani sebagai berkas biasa (bisa di-cache).
 *
 * Fase 30b: server otomatis mengompres (maks 1600 px, JPEG progresif), mencap watermark
 * konteks (`watermark` prop: proyek/kavling + tanggal WIB + organisasi), membuang metadata
 * EXIF/GPS, dan membuat thumbnail.
 *
 * Fase 32 (Papan Mandor): `capture` menampilkan tombol **Ambil foto** yang membuka kamera
 * belakang HP langsung — mandor tidak perlu keluar aplikasi. `geo` (bila diberikan)
 * dikirim bersama berkas sehingga koordinat pengambilan tersimpan terstruktur; metadata
 * EXIF tetap dibuang demi privasi.
 */
export default function PhotoUploader({
  value = [], onChange, ownerType = "generic", ownerId = null, max = 4,
  testId = FIELD.diaryPhotoInput, label = "Tambah foto", watermark = null,
  capture = false, geo = null, cameraTestId = BUILD.cameraInput,
}) {
  const [busy, setBusy] = useState(false);
  const [stats, setStats] = useState({});
  const [localPrev, setLocalPrev] = useState({});
  const inputRef = useRef(null);
  const camRef = useRef(null);

  // Fase 35 — simpan foto di perangkat saat sinyal hilang, lalu unggah otomatis nanti.
  const keepLocal = async (f) => {
    const id = await sync.storePhoto({
      blob: f, name: f.name, type: f.type, ownerId, watermark, geo,
    });
    setLocalPrev((m) => ({ ...m, [id]: URL.createObjectURL(f) }));
    return id;
  };

  const pick = async (e) => {
    const files = Array.from(e.target.files || []);
    if (e.target) e.target.value = "";
    if (!files.length) return;
    const room = max - value.length;
    if (room <= 0) {
      toast.error(`Maksimal ${max} foto.`);
      return;
    }
    setBusy(true);
    const added = [];
    const info = {};
    let stored = 0;
    try {
      for (const f of files.slice(0, room)) {
        if (f.size > MAX_MB * 1024 * 1024) {
          toast.error(`"${f.name}" lebih dari ${MAX_MB}MB — kompres dulu.`);
          continue;
        }
        if (!sync.isOnline()) {
          added.push(await keepLocal(f));
          stored += 1;
          continue;
        }
        const fd = new FormData();
        fd.append("file", f);
        fd.append("owner_type", ownerType);
        if (ownerId) fd.append("owner_id", ownerId);
        if (watermark) fd.append("watermark", watermark);
        if (geo?.lat && geo?.lng) {
          fd.append("lat", geo.lat);
          fd.append("lng", geo.lng);
          if (geo.accuracy) fd.append("accuracy", geo.accuracy);
          if (geo.captured_at) fd.append("captured_at", geo.captured_at);
        }
        try {
          const res = await api.post("/files/upload", fd);
          const rec = res.data?.data;
          if (rec?.id) {
            added.push(rec.id);
            info[rec.id] = { saving: rec.saving_pct || 0, kb: Math.round((rec.size || 0) / 1024),
              geo: !!rec.geo };
          }
        } catch (err) {
          // Tidak ada respons = jaringan putus di tengah jalan → jangan buang fotonya.
          if (err?.response) throw err;
          added.push(await keepLocal(f));
          stored += 1;
        }
      }
      if (added.length) {
        setStats((s) => ({ ...s, ...info }));
        onChange([...value, ...added]);
        const saved = added.map((id) => info[id]?.saving || 0).filter(Boolean);
        if (stored) {
          toast.success(`${stored} foto disimpan di perangkat — akan terunggah otomatis `
            + "begitu sinyal kembali.");
        }
        if (added.length - stored > 0) {
          toast.success(saved.length
            ? `${added.length - stored} foto terunggah · ukuran turun ${Math.round(
              saved.reduce((a, b) => a + b, 0) / saved.length)}% + watermark tercap.`
            : `${added.length - stored} foto terunggah.`);
        }
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Gagal mengunggah foto.");
    } finally {
      setBusy(false);
    }
  };

  const remove = (id) => onChange(value.filter((v) => v !== id));
  const full = value.length >= max;

  return (
    <div className="space-y-2">
      {capture ? (
        <div className="flex flex-wrap items-center gap-2">
          <input ref={camRef} type="file" accept="image/*" capture="environment" multiple
            data-testid={cameraTestId} className="hidden" onChange={pick}
            aria-label={`${label} (kamera)`} />
          <Button type="button" size="sm" disabled={busy || full}
            onClick={() => camRef.current?.click()}>
            <Camera className="mr-1.5 h-4 w-4" /> Ambil foto
          </Button>
          <Button type="button" size="sm" variant="outline" disabled={busy || full}
            onClick={() => inputRef.current?.click()}>
            <ImagePlus className="mr-1.5 h-4 w-4" /> Pilih berkas
          </Button>
          {busy ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /> : null}
        </div>
      ) : null}
      <div className={`flex items-center gap-2 ${capture ? "hidden" : ""}`}>
        <Input ref={inputRef} data-testid={testId} type="file" accept="image/*" multiple
          aria-label={label} disabled={busy || full} onChange={pick}
          className="h-auto cursor-pointer py-1.5 file:mr-2.5 file:cursor-pointer
            file:rounded-md file:border-0 file:bg-primary file:px-2.5 file:py-1
            file:text-xs file:font-semibold file:text-primary-foreground
            hover:file:bg-primary/90" />
        {busy && !capture ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        ) : null}
      </div>
      {capture ? (
        <input ref={inputRef} data-testid={testId} type="file" accept="image/*" multiple
          className="hidden" onChange={pick} aria-label={label} />
      ) : null}
      <p className="text-[11px] text-muted-foreground">
        {value.length}/{max} foto · maks {MAX_MB}MB per berkas · otomatis dikompres, diberi
        watermark {watermark ? `“${watermark}”` : "proyek + tanggal"}, dan metadata GPS dibuang.
        {geo?.lat ? " Koordinat pengambilan direkam terpisah." : ""}
      </p>
      {value.length ? (
        <div className="flex flex-wrap gap-2">
          {value.map((id) => (
            <div key={id} data-testid={FIELD.photoThumb}
              className="relative h-20 w-24 overflow-hidden rounded-md border bg-secondary">
              <img src={sync.isLocalPhoto(id) ? (localPrev[id] || "")
                : photoSrc(id, { variant: "thumb" })}
                alt="Pratinjau foto lapangan" className="h-full w-full object-cover" />
              {sync.isLocalPhoto(id) ? (
                <span data-testid={OFFLINE.photoLocal}
                  className="absolute left-0 top-0 bg-amber-600/90 px-1 text-[9px] font-semibold text-white">
                  tersimpan di HP
                </span>
              ) : null}
              {stats[id]?.saving ? (
                <span className="absolute bottom-0 left-0 bg-black/65 px-1 text-[9px] font-semibold text-white">
                  -{stats[id].saving}% · {stats[id].kb}KB
                </span>
              ) : null}
              {stats[id]?.geo ? (
                <span className="absolute bottom-0 right-0 bg-emerald-700/80 p-0.5 text-white">
                  <MapPin className="h-2.5 w-2.5" />
                </span>
              ) : null}
              <Button type="button" size="icon" variant="secondary"
                data-testid={FIELD.photoRemove} aria-label="Hapus foto"
                className="absolute right-0.5 top-0.5 h-5 w-5 rounded-full p-0 shadow"
                onClick={() => remove(id)}>
                <X className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex items-center gap-1.5 rounded-md border border-dashed bg-secondary/30 px-2.5 py-2 text-[11px] text-muted-foreground">
          <ImagePlus className="h-3.5 w-3.5" /> Belum ada foto dipilih.
        </div>
      )}
    </div>
  );
}
