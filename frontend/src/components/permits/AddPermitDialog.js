import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { PERMITS, PERMIT_COVERAGE } from "@/constants/testIds";

const EMPTY = {
  project_id: "", type: "IMB", name: "", reference_no: "", authority: "", deadline: "",
  notes: "", scope: "project", scope_id: "", expiry_at: "", requirement_code: "",
};

/**
 * Tambah izin — Fase 46 menambahkan tiga hal yang membuat izin berguna:
 *   1. **Cakupan objek** (proyek/cluster/blok/unit): izin PBG bisa per cluster, SLF per unit.
 *   2. **Masa berlaku** (`expiry_at`) — berbeda dari tenggat pengurusan (`deadline`).
 *      Dibiarkan kosong pun boleh, tetapi layar akan menulis “masa berlaku belum dicatat”
 *      alih-alih menganggap izin aman selamanya.
 *   3. **Kode dokumen syarat** agar izin bisa dipakai gerbang “mulai bangun”.
 */
export default function AddPermitDialog({ open, onOpenChange, projects, onDone,
  presetProjectId = null, presetScope = null, presetScopeId = null }) {
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [objects, setObjects] = useState([]);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (!open) return;
    setForm({
      ...EMPTY,
      project_id: presetProjectId || projects?.[0]?.id || "",
      scope: presetScope || "project",
      scope_id: presetScope && presetScope !== "project" ? (presetScopeId || "") : "",
    });
  }, [open, projects, presetProjectId, presetScope, presetScopeId]);

  // Daftar objek untuk cakupan terpilih diambil dari master (bukan diketik bebas), supaya
  // izin tidak pernah menempel pada objek yang tidak ada.
  const loadObjects = useCallback(async () => {
    if (!form.project_id || form.scope === "project") { setObjects([]); return; }
    try {
      if (form.scope === "cluster") {
        const r = await api.get(`/masterplan/projects/${form.project_id}/clusters`);
        setObjects((r.data.data || []).map((c) => ({
          id: c.id, label: `${c.code} — ${c.name || ""}`.trim() })));
      } else if (form.scope === "block") {
        const r = await api.get("/masterplan/blocks", {
          params: { project_id: form.project_id } });
        setObjects((r.data.data || []).map((b) => ({
          id: b.id, label: `${b.cluster_code || "-"} / ${b.code} — ${b.name || ""}`.trim() })));
      } else {
        const r = await api.get("/masterplan/units", {
          params: { project_id: form.project_id, limit: 200 } });
        setObjects((r.data.data || []).map((u) => ({
          id: u.id, label: `${u.code} · ${u.type || ""}`.trim() })));
      }
    } catch { setObjects([]); }
  }, [form.project_id, form.scope]);

  useEffect(() => { loadObjects(); }, [loadObjects]);

  const submit = async () => {
    if (!form.project_id) { toast.error("Pilih proyek."); return; }
    if (form.scope !== "project" && !form.scope_id) {
      toast.error("Pilih objek (cluster/blok/unit) untuk cakupan ini.");
      return;
    }
    setBusy(true);
    try {
      await api.post("/permits", {
        project_id: form.project_id, type: form.type,
        name: form.name || null, reference_no: form.reference_no || null,
        authority: form.authority || null, notes: form.notes || null,
        deadline: form.deadline ? new Date(form.deadline).toISOString() : null,
        expiry_at: form.expiry_at ? new Date(form.expiry_at).toISOString() : null,
        scope: form.scope, scope_id: form.scope === "project" ? null : form.scope_id,
        requirement_code: form.requirement_code || null,
      });
      toast.success("Perizinan ditambahkan.");
      onOpenChange(false); onDone && onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menambah perizinan."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto bg-card sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Tambah Perizinan</DialogTitle>
          <DialogDescription>
            Catat izin/dokumen legal beserta objek yang dilekatinya, tenggat pengurusan, dan
            masa berlakunya.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="permit-project">Proyek</Label>
            <Select value={form.project_id} onValueChange={(v) => set("project_id", v)}>
              <SelectTrigger id="permit-project" aria-label="Proyek"
                data-testid={PERMITS.formProject}>
                <SelectValue placeholder="Pilih proyek" />
              </SelectTrigger>
              <SelectContent>
                {(projects || []).map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Jenis</Label>
            <ReferenceSelect group="permit_type" value={form.type}
              onChange={(v) => set("type", v)} testId="permit-form-type" />
          </div>
          <div className="space-y-1.5">
            <Label>Cakupan (izin menempel pada)</Label>
            <ReferenceSelect group="permit_scope" value={form.scope}
              onChange={(v) => { set("scope", v); set("scope_id", ""); }}
              testId={PERMIT_COVERAGE.scopeSelect} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="permit-scope-object">Objek</Label>
            {form.scope === "project" ? (
              <p className="rounded-md border bg-secondary px-3 py-2 text-xs text-muted-foreground">
                Berlaku untuk SELURUH unit di proyek ini.
              </p>
            ) : (
              <Select value={form.scope_id} onValueChange={(v) => set("scope_id", v)}>
                <SelectTrigger id="permit-scope-object" aria-label="Objek"
                  data-testid={PERMIT_COVERAGE.scopeObject}>
                  <SelectValue placeholder="Pilih objek" />
                </SelectTrigger>
                <SelectContent>
                  {objects.map((o) => (
                    <SelectItem key={o.id} value={o.id}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="permit-name">Nama Dokumen</Label>
            <Input id="permit-name" data-testid="permit-form-name" value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="mis. Persetujuan Bangunan Gedung" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="permit-ref">No. Referensi</Label>
            <Input id="permit-ref" data-testid="permit-form-ref" value={form.reference_no}
              onChange={(e) => set("reference_no", e.target.value)}
              placeholder="mis. 503/1234/DPMPTSP/2026" />
          </div>
          <div className="space-y-1.5">
            <Label>Instansi</Label>
            <ReferenceSelect group="permit_authority" value={form.authority}
              onChange={(v) => set("authority", v)} testId="permit-form-authority"
              placeholder="Pilih instansi" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="permit-deadline">Tenggat pengurusan</Label>
            <Input id="permit-deadline" data-testid="permit-form-deadline" type="date"
              value={form.deadline} onChange={(e) => set("deadline", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="permit-expiry">Masa berlaku sampai</Label>
            <Input id="permit-expiry" data-testid={PERMIT_COVERAGE.expiry} type="date"
              value={form.expiry_at} onChange={(e) => set("expiry_at", e.target.value)} />
            <p className="text-[11px] text-muted-foreground">
              Boleh dikosongkan — layar akan menulis “masa berlaku belum dicatat”, bukan
              menganggap izin aman selamanya.
            </p>
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="permit-notes">Catatan</Label>
            <Textarea id="permit-notes" data-testid="permit-form-notes" rows={2}
              value={form.notes} onChange={(e) => set("notes", e.target.value)}
              placeholder="mis. syarat tambahan dari instansi" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Batal
          </Button>
          <Button data-testid={PERMITS.addSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
