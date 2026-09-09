import React, { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { OMNI, P97 } from "@/constants/testIds";

const emptyForm = () => ({ name: "", category: "utility", language: "id", body: "", variables: "", examples: {}, header_type: "none", header_text: "", header_sample_handle: "" });

/** Satu-satunya tempat menulis isi template WA (Pusat Konfigurasi › Integrasi WhatsApp › Template). */
export default function WaTemplateEditorDialog({ template, open, onOpenChange, onSaved }) {
  const { options } = useReference();
  const [form, setForm] = useState(emptyForm());
  const [busy, setBusy] = useState(false);
  const frozen = template?.meta_status === "APPROVED";

  useEffect(() => {
    if (!open) return;
    setForm(template ? {
      name: template.name, category: template.category, language: template.language || "id", body: template.body,
      variables: (template.variables || []).join(", "), examples: template.examples || {},
      header_type: template.header_type || "none", header_text: template.header_text || "",
      header_sample_handle: template.header_sample_handle || "",
    } : emptyForm());
  }, [template, open]);

  const varList = form.variables.split(",").map((v) => v.trim()).filter(Boolean);

  const save = async () => {
    if (!form.name.trim() || !form.body.trim()) { toast.error("Nama & isi template wajib diisi."); return; }
    setBusy(true);
    const payload = frozen ? {
      name: form.name.trim(),
      examples: Object.fromEntries(Object.entries(form.examples || {}).filter(([k, v]) => k && String(v || "").trim())),
      header_sample_handle: form.header_sample_handle || null,
    } : {
      name: form.name.trim(), category: form.category, language: form.language, body: form.body, variables: varList,
      examples: Object.fromEntries(Object.entries(form.examples || {}).filter(([k, v]) => k && String(v || "").trim())),
      header_type: form.header_type || "none", header_text: form.header_type === "text" ? form.header_text : null,
      header_sample_handle: form.header_sample_handle || null,
    };
    try {
      const r = template ? await api.put(`/wa-templates/${template.id}`, payload) : await api.post("/wa-templates", payload);
      (r.data.warnings || []).forEach((w) => toast.warning(w, { duration: 9000 }));
      toast.success(template ? "Template diperbarui." : "Template dibuat. Ajukan ke Meta bila sudah final.");
      onOpenChange(false); onSaved && onSaved();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan template.", { duration: 9000 }); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{template ? `Ubah template — ${template.name}` : "Template WA baru"}</DialogTitle>
          <DialogDescription>Variabel ditulis {"{{nama}}"} dan didaftarkan di kolom Variabel; setiap variabel butuh contoh nilai untuk Meta.</DialogDescription>
        </DialogHeader>
        {frozen ? (
          <p data-testid={P97.tmplFrozen} className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
            Template ini sudah <b>APPROVED di Meta</b>: isi, variabel, kategori, dan header dibekukan supaya parameter yang dikirim
            sama dengan yang disetujui. Yang masih boleh: nama tampilan & contoh nilai. Perubahan isi = buat template baru.
          </p>
        ) : null}
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="watpl-name">Nama template</Label>
            <Input id="watpl-name" data-testid={OMNI.tmplName} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            {!template ? <p className="text-[11px] text-muted-foreground">Kode dibentuk dari nama; nama yang sama dengan template lain ditolak.</p> : null}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Kategori</Label>
              <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })} disabled={frozen}>
                <SelectTrigger aria-label="Kategori template"><SelectValue /></SelectTrigger>
                <SelectContent>{options("wa_template_category").map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="watpl-lang">Bahasa</Label>
              <Input id="watpl-lang" value={form.language} disabled={frozen} onChange={(e) => setForm({ ...form, language: e.target.value })} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="watpl-body">Isi pesan</Label>
            <Textarea id="watpl-body" data-testid={OMNI.tmplBody} rows={4} value={form.body} disabled={frozen}
              onChange={(e) => setForm({ ...form, body: e.target.value })} placeholder="Halo {{nama}}, ..." />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="watpl-vars">Variabel (pisahkan koma)</Label>
            <Input id="watpl-vars" value={form.variables} disabled={frozen} onChange={(e) => setForm({ ...form, variables: e.target.value })} placeholder="nama, unit" />
            <p className="text-[11px] text-muted-foreground">Setiap {"{{variabel}}"} di isi pesan harus terdaftar di sini, dan sebaliknya — Meta menomori parameter dari daftar ini.</p>
          </div>
          {varList.length ? (
            <div className="space-y-1.5 rounded-lg border bg-secondary/40 p-2.5">
              <Label className="text-xs">Contoh isi tiap variabel (diwajibkan Meta saat pengajuan)</Label>
              {varList.map((v) => (
                <div key={v} className="grid grid-cols-[7rem_1fr] items-center gap-2">
                  <code className="text-xs">{"{{" + v + "}}"}</code>
                  <Input data-testid={P97.tmplExample} aria-label={`Contoh nilai ${v}`} className="h-8 text-sm" value={form.examples?.[v] || ""}
                    onChange={(e) => setForm({ ...form, examples: { ...(form.examples || {}), [v]: e.target.value } })}
                    placeholder={v === "nama" || v === "name" ? "Budi Santoso" : "contoh"} />
                </div>
              ))}
            </div>
          ) : null}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Header</Label>
              <Select value={form.header_type} onValueChange={(v) => setForm({ ...form, header_type: v })} disabled={frozen}>
                <SelectTrigger data-testid={P97.tmplHeader} aria-label="Header template"><SelectValue /></SelectTrigger>
                <SelectContent>{options("wa_template_header").map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            {form.header_type === "text" ? (
              <div className="space-y-1.5">
                <Label htmlFor="watpl-header-text">Teks header</Label>
                <Input id="watpl-header-text" value={form.header_text} disabled={frozen} onChange={(e) => setForm({ ...form, header_text: e.target.value })} />
              </div>
            ) : null}
            {form.header_type === "document" || form.header_type === "image" ? (
              <div className="space-y-1.5">
                <Label htmlFor="watpl-header-handle">Contoh header (handle Meta)</Label>
                <Input id="watpl-header-handle" value={form.header_sample_handle} onChange={(e) => setForm({ ...form, header_sample_handle: e.target.value })} placeholder="4::aW1hZ2UvcG5n…" />
              </div>
            ) : null}
          </div>
          {form.header_type === "document" ? (
            <p className="text-[11px] text-muted-foreground">Template UTILITY berheader dokumen dipakai “Kirim via WhatsApp” di Dokumen Terbit saat sesi 24 jam tertutup. Meta mewajibkan contoh berkas (handle Resumable Upload) saat pengajuan.</p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={OMNI.tmplSave} onClick={save} disabled={busy}>{busy ? "Menyimpan…" : "Simpan"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
