import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Paperclip, Upload, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api from "@/services/apiClient";
import { P62 } from "@/constants/testIds";

const KINDS = [
  ["gambar_kerja", "Gambar kerja"],
  ["spesifikasi", "Spesifikasi teknis"],
  ["lainnya", "Lampiran lain"],
];

/**
 * SpkAttachmentsSection — lampiran SPK (Fase 62).
 *
 * Pasal 1 SPK menyebut pekerjaan dilaksanakan "sesuai gambar dan spesifikasi yang menjadi
 * lampiran surat ini" — sampai Fase 61 lampiran itu tidak pernah ada. Berkas yang diunggah
 * di sini IKUT TERCETAK sebagai halaman lampiran pada PDF SPK, jadi surat yang dipegang
 * subkontraktor lengkap dengan acuan kerjanya.
 */
export default function SpkAttachmentsSection({ spk, canManage, onChanged }) {
  const [rows, setRows] = useState([]);
  const [kind, setKind] = useState("gambar_kerja");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!spk?.id) return;
    try {
      const res = await api.get(`/subcon/spk/${spk.id}/attachments`);
      setRows(res.data.data || []);
    } catch { setRows([]); }
  }, [spk]);
  useEffect(() => { load(); }, [load]);

  const pick = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("owner_type", "spk_attachment");
      fd.append("owner_id", spk.id);
      fd.append("optimize", "false");
      const up = await api.post("/files/upload", fd,
        { headers: { "Content-Type": "multipart/form-data" } });
      await api.post(`/subcon/spk/${spk.id}/attachments`,
        { file_id: up.data.data.id, kind, label: file.name });
      toast.success("Lampiran ditambahkan — akan tercetak pada SPK.");
      load(); onChanged && onChanged();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Gagal menambahkan lampiran.");
    } finally { setBusy(false); e.target.value = ""; }
  };

  const remove = async (id) => {
    try {
      await api.delete(`/subcon/spk/${spk.id}/attachments/${id}`);
      toast.success("Lampiran dihapus dari SPK.");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menghapus lampiran."); }
  };

  const label = (k) => (KINDS.find(([v]) => v === k) || [k, k])[1];

  return (
    <div data-testid={P62.attachSection} className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <p className="flex items-center gap-1.5 text-sm font-semibold">
        <Paperclip className="h-4 w-4 text-primary" /> Lampiran SPK (gambar kerja &amp; spesifikasi)
      </p>
      <p className="text-[12px] text-muted-foreground">
        Berkas di sini ikut tercetak sebagai halaman lampiran pada PDF SPK — dasar yang
        dipegang subkontraktor saat bekerja dan saat pekerjaannya diperiksa.
      </p>

      {canManage ? (
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[12rem]">
            <Label className="text-[11px]">Jenis lampiran</Label>
            <Select value={kind} onValueChange={setKind}>
              <SelectTrigger data-testid={P62.attachKind}><SelectValue /></SelectTrigger>
              <SelectContent>
                {KINDS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <Button size="sm" variant="outline" asChild disabled={busy}>
            <label data-testid={P62.attachUpload} className="cursor-pointer">
              <Upload className="mr-1.5 inline h-3.5 w-3.5" />
              {busy ? "Mengunggah…" : "Unggah berkas"}
              <input type="file" className="hidden" onChange={pick}
                accept="image/*,application/pdf" />
            </label>
          </Button>
        </div>
      ) : null}

      {!rows.length ? (
        <p data-testid={P62.attachEmpty} className="text-[12px] text-muted-foreground">
          Belum ada lampiran. SPK yang dicetak akan menyebut gambar &amp; spesifikasi tetapi
          tidak melampirkannya.
        </p>
      ) : (
        <div className="divide-y rounded-lg border">
          {rows.map((a) => (
            <div key={a.id} data-testid={P62.attachRow} data-kind={a.kind}
              className="flex items-center justify-between gap-2 p-2.5">
              <div className="min-w-0 text-[12px]">
                <p className="truncate font-medium">{a.label || a.filename}</p>
                <p className="text-muted-foreground">
                  {label(a.kind)} · {String(a.created_at || "").slice(0, 10)}
                </p>
              </div>
              {canManage ? (
                <Button size="icon" variant="ghost" data-testid={P62.attachRemove}
                  aria-label={`Hapus lampiran ${a.label || a.filename}`}
                  onClick={() => remove(a.id)}>
                  <Trash2 className="h-3.5 w-3.5 text-rose-600" />
                </Button>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
