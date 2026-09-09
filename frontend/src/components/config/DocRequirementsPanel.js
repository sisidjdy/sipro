import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Pencil, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import DataTable from "@/components/patterns/DataTable";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import StatusPill from "@/components/patterns/StatusPill";
import api from "@/services/apiClient";
import { useReference } from "@/context/ReferenceContext";
import { CONFIG } from "@/constants/testIds";

// Daftar konteks syarat dokumen datang dari SSOT `/api/reference` grup `doc_context`
// (dulu ditulis ulang di sini sebagai CONTEXT_OPTIONS — dua sumber untuk satu vocabulary).

const EMPTY = {
  code: "", label: "", group: "identitas", applies_to: [], mandatory: true,
  conditional_note: "", max_mb: 10, needs_verification: true, order: 0, active: true,
};

/** Master dokumen syarat — keputusan owner D3: bisa ditambah admin, per tahap/skema. */
export default function DocRequirementsPanel() {
  const { labelOf, options } = useReference();
  const contextOptions = options("doc_context");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState({ q: "", sort: "order", direction: "asc", skip: 0, limit: 50 });
  const [context, setContext] = useState("");
  const [form, setForm] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/doc/requirements", {
        params: { context: context || undefined },
      });
      setRows(res.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat dokumen syarat.");
    } finally { setLoading(false); }
  }, [context]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const q = (query.q || "").toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => `${r.code} ${r.label} ${r.group}`.toLowerCase().includes(q));
  }, [rows, query.q]);

  const submit = async () => {
    try {
      if (form.id) {
        const { code, ...patch } = form;
        await api.put(`/doc/requirements/${form.id}`, patch);
      } else {
        await api.post("/doc/requirements", form);
      }
      toast.success("Dokumen syarat disimpan.");
      setForm(null); load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan.");
    }
  };

  const toggleContext = (value) => setForm((f) => {
    const list = new Set(f.applies_to || []);
    if (list.has(value)) list.delete(value); else list.add(value);
    return { ...f, applies_to: [...list] };
  });

  const columns = [
    { key: "code", header: "Kode", sortable: true,
      render: (r) => <span className="font-mono text-xs">{r.code}</span> },
    { key: "label", header: "Nama dokumen", sortable: true,
      render: (r) => (
        <div>
          <div className="font-medium">{r.label}</div>
          {r.conditional_note ? (
            <div className="text-xs text-muted-foreground">{r.conditional_note}</div>
          ) : null}
        </div>
      ) },
    { key: "group", header: "Kelompok", sortable: true,
      render: (r) => labelOf("doc_requirement_group", r.group) },
    { key: "applies_to", header: "Berlaku pada",
      render: (r) => (
        <div className="flex flex-wrap gap-1">
          {(r.applies_to || []).map((c) => (
            <span key={c} className="rounded border bg-secondary px-1.5 py-0.5 text-[10px]">
              {labelOf("doc_context", c)}
            </span>
          ))}
        </div>
      ),
      exportValue: (r) => (r.applies_to || []).join(" | ") },
    { key: "mandatory", header: "Wajib",
      render: (r) => <StatusPill status={r.mandatory ? "active" : "pending"}
        label={r.mandatory ? "Wajib" : "Opsional"} />,
      exportValue: (r) => (r.mandatory ? "wajib" : "opsional") },
    { key: "actions", header: "Aksi", align: "right", sticky: true, sticky: true,
      render: (r) => (
        <Button data-testid={CONFIG.docsEdit} size="sm" variant="ghost"
          onClick={() => setForm({ ...EMPTY, ...r })}>
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      ), exportValue: () => "" },
  ];

  return (
    <div data-testid={CONFIG.docsPanel} className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Syarat dokumen menentukan checklist yang harus dipenuhi sebelum tahap berikutnya
          (mis. SPR tidak bisa terbit sebelum dokumen wajib terverifikasi).
        </p>
        <Button data-testid={CONFIG.docsAdd} size="sm" onClick={() => setForm({ ...EMPTY })}>
          <Plus className="mr-1.5 h-4 w-4" /> Dokumen syarat baru
        </Button>
      </div>
      <DataTable
        testId="config-docs-table"
        testIds={{ search: "config-docs-search", row: CONFIG.docsRow,
          export: "config-docs-export", columns: "config-docs-columns" }}
        columns={columns} rows={filtered} total={filtered.length} query={query}
        onQueryChange={(p) => setQuery((q) => ({ ...q, ...p }))}
        loading={loading} error={error} onRefresh={load}
        searchPlaceholder="Cari dokumen syarat…" exportName="dokumen-syarat"
        emptyTitle="Belum ada dokumen syarat"
        emptyDescription="Tambahkan syarat dokumen agar checklist tahap bisa dijalankan."
        filters={(
          <select data-testid="config-docs-context" aria-label="Filter konteks"
            className="h-9 rounded-md border bg-background px-2 text-sm"
            value={context} onChange={(e) => setContext(e.target.value)}>
            <option value="">Semua konteks</option>
            {contextOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        )}
      />

      <Dialog open={!!form} onOpenChange={(o) => { if (!o) setForm(null); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{form?.id ? "Ubah dokumen syarat" : "Dokumen syarat baru"}</DialogTitle>
            <DialogDescription>
              Konteks menentukan di tahap mana dokumen ini diminta.
            </DialogDescription>
          </DialogHeader>
          {form ? (
            <div className="max-h-[60vh] space-y-3 overflow-y-auto pr-1">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="doc-code">Kode</Label>
                  <Input id="doc-code" data-testid={CONFIG.docsFormCode} value={form.code}
                    disabled={!!form.id} placeholder="KTP"
                    onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="doc-order">Urutan tampil</Label>
                  <Input id="doc-order" type="number" value={form.order}
                    onChange={(e) => setForm({ ...form, order: Number(e.target.value) })} />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="doc-label">Nama dokumen</Label>
                <Input id="doc-label" data-testid={CONFIG.docsFormLabel} value={form.label}
                  placeholder="KTP pemesan"
                  onChange={(e) => setForm({ ...form, label: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label>Kelompok dokumen</Label>
                <ReferenceSelect group="doc_requirement_group" value={form.group}
                  testId={CONFIG.docsFormGroup}
                  onChange={(v) => setForm({ ...form, group: v })} />
              </div>
              <div className="space-y-1.5">
                <Label>Berlaku pada konteks</Label>
                <div data-testid={CONFIG.docsFormContexts}
                  className="grid gap-1.5 rounded-md border bg-secondary p-2 sm:grid-cols-2">
                  {contextOptions.map((o) => (
                    <label key={o.value} className="flex items-center gap-2 text-xs">
                      <input type="checkbox" checked={(form.applies_to || []).includes(o.value)}
                        onChange={() => toggleContext(o.value)} />
                      {o.label}
                    </label>
                  ))}
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="doc-note">Catatan syarat (opsional)</Label>
                <Textarea id="doc-note" rows={2} value={form.conditional_note || ""}
                  placeholder="Wajib bila pemesan sudah menikah"
                  onChange={(e) => setForm({ ...form, conditional_note: e.target.value })} />
              </div>
              <div className="flex flex-wrap items-center gap-6">
                <div className="flex items-center gap-2">
                  <Switch data-testid={CONFIG.docsFormMandatory} checked={!!form.mandatory}
                    aria-label="Wajib" onCheckedChange={(v) => setForm({ ...form, mandatory: v })} />
                  <span className="text-sm">Wajib</span>
                </div>
                <div className="flex items-center gap-2">
                  <Switch checked={!!form.needs_verification} aria-label="Perlu verifikasi"
                    onCheckedChange={(v) => setForm({ ...form, needs_verification: v })} />
                  <span className="text-sm">Perlu verifikasi</span>
                </div>
                <div className="flex items-center gap-2">
                  <Switch checked={!!form.active} aria-label="Aktif"
                    onCheckedChange={(v) => setForm({ ...form, active: v })} />
                  <span className="text-sm">Aktif</span>
                </div>
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setForm(null)}>Batal</Button>
            <Button data-testid={CONFIG.docsSubmit} onClick={submit}
              disabled={!form?.code || !form?.label}>Simpan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
