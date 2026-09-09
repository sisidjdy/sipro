import React, { useState } from "react";
import { toast } from "sonner";
import { Plus } from "lucide-react";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import DocLayoutPanel from "@/components/master/DocLayoutPanel";
import api from "@/services/apiClient";
import { MASTER } from "@/constants/testIds";

const EMPTY = { code: "", name: "", content: "" };

/**
 * DocTemplatesPanel — TEMPLATE DOKUMEN: satu layar untuk satu jenis dokumen (Fase 66).
 *
 * Sebelum ini layar ini punya DUA tab yang tidak saling tahu: "Isi template (naskah)" berisi
 * daftar naskah berkode bebas, dan "Tampilan & kop surat" berisi konfigurasi per dokumen.
 * Pemakai harus menebak naskah mana yang dipakai dokumen mana, dan pratinjau tidak pernah
 * menampilkan naskahnya. Sekarang keduanya SATU: pilih jenis dokumennya, lalu setel naskah,
 * kop, baris biaya, gaya tabel, dan tanda tangan berdampingan dengan pratinjau.
 *
 * Yang tersisa di sini hanya pembuatan JENIS dokumen baru (kode + nama + naskah awal) —
 * sesudah dibuat, dokumen itu muncul di pemilih jenis pada panel di bawah.
 */
function AddDocumentDialog({ open, onOpenChange, onDone }) {
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.code.trim() || !form.name.trim()) {
      toast.error("Kode dan nama jenis dokumen wajib diisi."); return;
    }
    setBusy(true);
    try {
      await api.post("/master/doc-templates", {
        code: form.code.trim().toUpperCase(), name: form.name.trim(),
        content: form.content || form.name.trim(),
      });
      toast.success(`Jenis dokumen ${form.code.toUpperCase()} dibuat.`);
      setForm(EMPTY);
      onOpenChange(false);
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membuat jenis dokumen.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Tambah jenis dokumen</DialogTitle>
          <DialogDescription>
            Naskah lengkap, kop surat, dan gaya tabelnya disetel setelah ini pada panel
            konfigurasi — jenis dokumen baru akan muncul di pemilih jenis dokumen.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="doc-type-code">Kode jenis dokumen</Label>
            <Input id="doc-type-code" data-testid={MASTER.docFormCode} value={form.code}
              placeholder="mis. SURAT_KUASA"
              onChange={(e) => set("code", e.target.value.toUpperCase())} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="doc-type-name">Nama jenis dokumen</Label>
            <Input id="doc-type-name" data-testid={MASTER.docFormName} value={form.name}
              placeholder="mis. Surat Kuasa Pengurusan Sertifikat"
              onChange={(e) => set("name", e.target.value)} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="doc-type-content">Naskah awal (bisa diubah nanti)</Label>
            <Textarea id="doc-type-content" data-testid={MASTER.docFormContent} rows={6}
              className="font-mono text-[12px]" value={form.content}
              placeholder={"Yang bertanda tangan di bawah ini …"}
              onChange={(e) => set("content", e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Batal
          </Button>
          <Button data-testid={MASTER.docSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function DocTemplatesPanel() {
  const [open, setOpen] = useState(false);
  const [nonce, setNonce] = useState(0);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Satu layar per jenis dokumen: naskah yang tercetak, kop surat, baris biaya, gaya
          tabel, dan tanda tangan — dengan pratinjau yang memakai mesin cetak sungguhan.
        </p>
        <Button data-testid={MASTER.docAddBtn} size="sm" onClick={() => setOpen(true)}>
          <Plus className="mr-1.5 h-4 w-4" /> Tambah jenis dokumen
        </Button>
      </div>
      <DocLayoutPanel key={nonce} />
      <AddDocumentDialog open={open} onOpenChange={setOpen}
        onDone={() => setNonce((n) => n + 1)} />
    </div>
  );
}
