import React, { useRef, useState } from "react";
import { FileText, ImageIcon, Loader2, Paperclip, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import api from "@/services/apiClient";
import { fileUrl } from "@/utils/photoSrc";

const MAX_MB = 8;

/**
 * EvidenceUploader — unggah BUKTI (tangkapan layar atau PDF) lalu simpan `file_id`.
 *
 * Beda dari `PhotoUploader`: berkas bukti TIDAK dikompres/diberi watermark
 * (`optimize=false`) karena dokumen bukti harus tetap apa adanya untuk audit —
 * mengubah berkas bukti sama dengan merusak nilai buktinya.
 */
export default function EvidenceUploader({
  value = [], onChange, ownerType = "generic", ownerId = null, max = 3,
  testId = "evidence-input", label = "Lampirkan bukti", accept = "image/*,application/pdf",
  names = {}, hint = null,
}) {
  const [busy, setBusy] = useState(false);
  const [meta, setMeta] = useState({});
  const inputRef = useRef(null);

  const pick = async (e) => {
    const files = Array.from(e.target.files || []);
    if (inputRef.current) inputRef.current.value = "";
    if (!files.length) return;
    const room = max - value.length;
    if (room <= 0) {
      toast.error(`Maksimal ${max} lampiran.`);
      return;
    }
    setBusy(true);
    const added = [];
    const info = {};
    try {
      for (const f of files.slice(0, room)) {
        if (f.size > MAX_MB * 1024 * 1024) {
          toast.error(`"${f.name}" lebih dari ${MAX_MB}MB.`);
          continue;
        }
        const fd = new FormData();
        fd.append("file", f);
        fd.append("owner_type", ownerType);
        fd.append("optimize", "false");
        if (ownerId) fd.append("owner_id", ownerId);
        const res = await api.post("/files/upload", fd);
        const rec = res.data?.data;
        if (rec?.id) {
          added.push(rec.id);
          info[rec.id] = { name: rec.original_filename || f.name, type: rec.content_type };
        }
      }
      if (added.length) {
        setMeta((m) => ({ ...m, ...info }));
        onChange([...value, ...added]);
        toast.success(`${added.length} lampiran terunggah.`);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Gagal mengunggah lampiran.");
    } finally {
      setBusy(false);
    }
  };

  const remove = (id) => onChange(value.filter((v) => v !== id));
  const nameOf = (id) => meta[id]?.name || names[id] || `Lampiran ${String(id).slice(0, 6)}`;
  const isPdf = (id) => String(meta[id]?.type || names[id] || "").toLowerCase().includes("pdf");

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Input ref={inputRef} data-testid={testId} type="file" accept={accept} multiple
          aria-label={label} disabled={busy || value.length >= max} onChange={pick}
          className="cursor-pointer file:mr-2 file:cursor-pointer" />
        {busy ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /> : null}
      </div>
      <p className="text-[11px] text-muted-foreground">
        {value.length}/{max} lampiran · {hint || `gambar atau PDF · maks ${MAX_MB}MB · disimpan utuh (tanpa kompresi) agar sah sebagai bukti.`}
      </p>
      {value.length ? (
        <div className="flex flex-wrap gap-1.5">
          {value.map((id) => (
            <span key={id} data-testid="evidence-chip" data-file={id}
              className="flex max-w-full items-center gap-1.5 rounded-full border bg-secondary px-2 py-1 text-[11px]">
              {isPdf(id) ? <FileText className="h-3.5 w-3.5 shrink-0 text-rose-600" />
                : <ImageIcon className="h-3.5 w-3.5 shrink-0 text-primary" />}
              <a href={fileUrl(id)} target="_blank" rel="noreferrer"
                className="max-w-[160px] truncate underline-offset-2 hover:underline">
                {nameOf(id)}
              </a>
              <Button type="button" size="icon" variant="ghost" data-testid="evidence-remove"
                data-file={id} aria-label={`Hapus lampiran ${nameOf(id)}`}
                className="h-4 w-4 rounded-full p-0" onClick={() => remove(id)}>
                <X className="h-3 w-3" />
              </Button>
            </span>
          ))}
        </div>
      ) : (
        <div className="flex items-center gap-1.5 rounded-md border border-dashed bg-secondary/30 px-2.5 py-2 text-[11px] text-muted-foreground">
          <Paperclip className="h-3.5 w-3.5" /> Belum ada lampiran dipilih.
        </div>
      )}
    </div>
  );
}
