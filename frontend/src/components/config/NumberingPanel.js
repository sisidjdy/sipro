import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Hash, Pencil } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import DataTable from "@/components/patterns/DataTable";
import NumberingRuleDialog from "@/components/config/NumberingRuleDialog";
import api from "@/services/apiClient";
import { useAuth } from "@/context/AuthContext";
import { NUMBERING } from "@/constants/testIds";

/**
 * NumberingPanel — Pusat Konfigurasi › Penomoran (Fase 71).
 * Satu baris per jenis nomor dokumen / kode master; pola diubah lewat dialog dengan pratinjau
 * hidup. Nomor yang sudah terbit tidak berubah — aturan hanya untuk nomor berikutnya.
 */
export default function NumberingPanel() {
  const { can } = useAuth();
  const canEdit = can("settings", "update");
  const [meta, setMeta] = useState({ rows: [], groups: [], resetOptions: [], scopeOptions: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [group, setGroup] = useState("all");
  const [query, setQuery] = useState({ q: "", sort: "group_label", direction: "asc", skip: 0, limit: 100 });
  const [editing, setEditing] = useState(null);
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/numbering", { params: projectId ? { project_id: projectId } : {} });
      setMeta({
        rows: res.data.data || [], groups: res.data.groups || [],
        resetOptions: res.data.reset_options || [], scopeOptions: res.data.seq_scope_options || [],
      });
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat aturan penomoran.");
    } finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get("/projects").then((r) => setProjects(r.data.data || [])).catch(() => {});
  }, []);

  const rows = useMemo(() => {
    const q = (query.q || "").toLowerCase();
    return meta.rows.filter((r) => (group === "all" || r.group === group)
      && (!q || `${r.label} ${r.key} ${r.pattern} ${r.preview}`.toLowerCase().includes(q)));
  }, [meta.rows, group, query.q]);

  const resetLabel = (v) => meta.resetOptions.find((o) => o.value === v)?.label || v;

  const columns = [
    { key: "label", header: "Jenis nomor", sortable: true,
      render: (r) => (
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium">{r.label}</span>
            {r.overridden ? (
              <Badge data-testid={NUMBERING.overriddenBadge} variant="outline"
                className="border-amber-300 bg-amber-50 text-[10px] text-amber-800">disesuaikan</Badge>
            ) : null}
          </div>
          <div className="text-[11px] text-muted-foreground">{r.group_label}{r.desc ? ` · ${r.desc}` : ""}</div>
        </div>
      ) },
    { key: "pattern", header: "Pola", render: (r) => <code className="text-xs">{r.pattern}</code> },
    { key: "preview", header: projectId ? "Nomor berikutnya (proyek terpilih)" : "Contoh nomor berikutnya (urutan dasar)",
      render: (r) => <span className="font-mono text-xs font-semibold">{r.preview}</span> },
    { key: "reset", header: "Reset", render: (r) => resetLabel(r.reset) },
    { key: "next_seq", header: "Urut berikutnya", align: "right" },
    { key: "actions", header: "Aksi", align: "right", sticky: true, exportValue: () => "",
      render: (r) => (
        <Button data-testid={NUMBERING.edit} size="sm" variant="ghost" aria-label={`Ubah ${r.label}`}
          onClick={() => setEditing(r)}>
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      ) },
  ];

  return (
    <div data-testid={NUMBERING.panel} className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-3xl text-sm text-muted-foreground">
          <Hash className="mr-1 inline h-3.5 w-3.5" />
          Format nomor dokumen (SPK, PO, kwitansi, PPJB…) dan kode master (proyek, blok, unit,
          vendor…) disusun dari <strong>pola + token</strong>, mis. <code>{"{PREFIX}/{PROJECT_CODE}/{MM_ROMAN}/{YYYY}/{SEQ}"}</code>.
          Urutan bisa dipisah per proyek/vendor bila pola memuat token konteksnya (contoh di tabel
          memakai urutan dasar organisasi & nilai token contoh). Nomor yang sudah terbit tidak
          pernah berubah.
        </p>
        <div className="flex flex-wrap gap-2">
        <Select value={projectId || "__none"} onValueChange={(v) => setProjectId(v === "__none" ? "" : v)}>
          <SelectTrigger data-testid={NUMBERING.projectFilter} className="w-60" aria-label="Proyek contoh">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none">Contoh umum (nilai token contoh)</SelectItem>
            {projects.map((p) => <SelectItem key={p.id} value={p.id}>Pratinjau proyek: {p.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={group} onValueChange={setGroup}>
          <SelectTrigger data-testid={NUMBERING.groupFilter} className="w-56" aria-label="Kelompok aturan">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Semua kelompok</SelectItem>
            {meta.groups.map((g) => <SelectItem key={g.key} value={g.key}>{g.label}</SelectItem>)}
          </SelectContent>
        </Select>
        </div>
      </div>
      <DataTable
        testId={NUMBERING.table}
        testIds={{ search: NUMBERING.search, row: NUMBERING.row,
          export: "numbering-export", columns: "numbering-columns" }}
        columns={columns} rows={rows} total={rows.length} query={query}
        onQueryChange={(p) => setQuery((q) => ({ ...q, ...p }))}
        loading={loading} error={error} onRefresh={load}
        searchPlaceholder="Cari jenis nomor, pola, atau contoh…" exportName="aturan-penomoran"
        emptyTitle="Tidak ada aturan yang cocok" />
      {editing ? (
        <NumberingRuleDialog rule={editing} canEdit={canEdit} projectId={projectId}
          resetOptions={meta.resetOptions} scopeOptions={meta.scopeOptions}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
      ) : null}
    </div>
  );
}
