import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ClipboardCheck, Plus, Pencil, Archive, Trash2, AlertTriangle } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import ConfirmDialog from "@/components/patterns/ConfirmDialog";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { MASTER } from "@/constants/testIds";

function TemplateDialog({ open, onOpenChange, initial, onDone }) {
  const editing = Boolean(initial?.id);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [category, setCategory] = useState("lainnya");
  const [items, setItems] = useState([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setCode(initial?.code || "");
    setName(initial?.name || "");
    setCategory(initial?.category || "lainnya");
    setItems((initial?.items || []).map((i) => ({ label: i.label, critical: Boolean(i.critical) })));
    setDraft("");
  }, [open, initial]);

  const addItem = () => {
    const label = draft.trim();
    if (!label) return;
    setItems((xs) => [...xs, { label, critical: false }]);
    setDraft("");
  };

  const submit = async () => {
    if (!name.trim() || (!editing && !code.trim())) { toast.error("Kode & nama wajib diisi."); return; }
    if (!items.length) { toast.error("Tambahkan minimal 1 item checklist."); return; }
    setBusy(true);
    try {
      if (editing) {
        await api.put(`/master/qc-templates/${initial.id}`, { name, category, items });
        toast.success("Template QC diperbarui.");
      } else {
        await api.post("/master/qc-templates", { code, name, category, items });
        toast.success("Template QC dibuat.");
      }
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan template QC."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{editing ? "Ubah Template QC" : "Tambah Template QC"}</DialogTitle>
          <DialogDescription>Checklist yang dipakai saat membuat inspeksi mutu.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="qctemplatespanel-kode">Kode</Label>
            <Input id="qctemplatespanel-kode" data-testid={MASTER.qcFormCode} value={code} disabled={editing}
              onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="mis. QC-ARS" />
          </div>
          <div className="space-y-1.5">
            <Label>Kategori</Label>
            <ReferenceSelect group="inspection_category" value={category} onChange={setCategory}
              testId={MASTER.qcFormCategory} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="qctemplatespanel-nama">Nama</Label>
            <Input id="qctemplatespanel-nama" data-testid={MASTER.qcFormName} value={name}
              onChange={(e) => setName(e.target.value)} placeholder="mis. Inspeksi Arsitektur" />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label>Item Checklist ({items.length})</Label>
            <div className="flex gap-2">
              <Input data-testid={MASTER.qcItemInput} value={draft} onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addItem(); } }}
                placeholder="mis. Plesteran rata & tidak keropos" />
              <Button data-testid={MASTER.qcItemAdd} type="button" variant="secondary" onClick={addItem}>
                Tambah
              </Button>
            </div>
            {items.length ? (
              <div className="space-y-1.5 rounded-lg border bg-card p-2 shadow-[var(--shadow-card)]">
                {items.map((it, i) => (
                  <div key={`${it.label}-${i}`} className="flex items-center justify-between gap-2 text-sm">
                    <span className="flex items-center gap-2">
                      {it.critical ? <AlertTriangle className="h-3.5 w-3.5 text-amber-600" /> : null}
                      {it.label}
                    </span>
                    <span className="flex items-center gap-3">
                      <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Checkbox checked={it.critical}
                          onCheckedChange={(v) => setItems((xs) => xs.map((x, idx) =>
                            (idx === i ? { ...x, critical: Boolean(v) } : x)))} />
                        kritis
                      </label>
                      <Button type="button" size="icon" variant="ghost" className="h-7 w-7"
                        onClick={() => setItems((xs) => xs.filter((_, idx) => idx !== i))}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">Belum ada item.</p>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Batal</Button>
          <Button data-testid={MASTER.qcSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function QcTemplatesPanel() {
  const { labelOf } = useReference();
  const [rows, setRows] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dlg, setDlg] = useState({ open: false, initial: null });
  const [archiveTarget, setArchiveTarget] = useState(null);
  const [archiveBusy, setArchiveBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const r = await api.get("/master/qc-templates", { params: { include_inactive: true } });
      setRows(r.data.data || []);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat template QC."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const archive = async () => {
    const t = archiveTarget;
    if (!t) return;
    setArchiveBusy(true);
    try {
      await api.delete(`/master/qc-templates/${t.id}`);
      toast.success(`Template ${t.code} diarsipkan.`);
      setArchiveTarget(null);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengarsipkan."); }
    finally { setArchiveBusy(false); }
  };

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Checklist inspeksi mutu per kategori pekerjaan. Item bertanda kritis menggagalkan inspeksi.
        </p>
        <Button data-testid={MASTER.qcAddBtn} size="sm" onClick={() => setDlg({ open: true, initial: null })}>
          <Plus className="mr-1.5 h-4 w-4" /> Tambah Template
        </Button>
      </div>
      {!rows?.length ? (
        <EmptyState icon={ClipboardCheck} title="Belum ada template QC"
          description="Buat checklist QC pertama agar inspeksi bisa dijalankan."
          actionLabel="Tambah Template" onAction={() => setDlg({ open: true, initial: null })} />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {rows.map((t) => (
            <div key={t.id} data-testid={MASTER.qcRow} data-template-code={t.code}
              data-template-archived={t.is_active === false ? "true" : "false"}
              className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-heading text-sm font-semibold">{t.name}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {t.code} · {labelOf("inspection_category", t.category)} · {(t.items || []).length} item
                    {t.is_active === false ? " · diarsipkan" : ""}
                  </p>
                </div>
                <div className="flex gap-1">
                  <Button data-testid={MASTER.qcEditBtn} data-template-code={t.code}
                    aria-label={`Ubah template QC ${t.code}`} title={`Ubah template ${t.code}`}
                    size="sm" variant="outline"
                    onClick={() => setDlg({ open: true, initial: t })}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  {t.is_active !== false ? (
                    <Button data-testid={MASTER.qcArchiveBtn} data-template-code={t.code}
                      aria-label={`Arsipkan template QC ${t.code}`} title={`Arsipkan template ${t.code}`}
                      size="sm" variant="ghost" onClick={() => setArchiveTarget(t)}>
                      <Archive className="h-3.5 w-3.5" />
                    </Button>
                  ) : null}
                </div>
              </div>
              <ul className="mt-2 space-y-0.5 text-xs text-muted-foreground">
                {(t.items || []).slice(0, 5).map((i, idx) => (
                  <li key={`${t.id}-${idx}`}>• {i.label}{i.critical ? " (kritis)" : ""}</li>
                ))}
                {(t.items || []).length > 5 ? <li>…</li> : null}
              </ul>
            </div>
          ))}
        </div>
      )}
      <TemplateDialog open={dlg.open} initial={dlg.initial}
        onOpenChange={(o) => setDlg((d) => ({ ...d, open: o }))} onDone={load} />
      <ConfirmDialog open={!!archiveTarget} onOpenChange={(v) => !v && setArchiveTarget(null)}
        title={`Arsipkan template “${archiveTarget?.name || ""}”?`}
        description="Template yang diarsipkan tidak lagi muncul saat membuat inspeksi baru, tetapi inspeksi yang sudah ada tetap utuh."
        confirmLabel="Ya, arsipkan" busy={archiveBusy} onConfirm={archive}
        testId="qc-archive-confirm" />
    </div>
  );
}
