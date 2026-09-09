import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { History, RotateCcw, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import DataTable from "@/components/patterns/DataTable";
import api from "@/services/apiClient";
import { formatDateTimeWIB } from "@/utils/formatters";
import { useReference } from "@/context/ReferenceContext";
import { CONFIG } from "@/constants/testIds";

// Label asal & dasar nilai setting datang dari SSOT `/api/reference`
// (grup `setting_origin` & `setting_source`) — dulu dua peta label kembar di sini,
// sehingga mengganti kata "Diubah organisasi" harus dikerjakan di dua tempat.

function valueText(row) {
  const v = row.value;
  if (row.type === "bool") return v ? "Aktif" : "Tidak aktif";
  if (row.type === "money") return new Intl.NumberFormat("id-ID").format(Number(v) || 0);
  if (row.type === "pct") return `${v}%`;
  if (row.type === "enum") return row.option_labels?.[v] || String(v);
  if (Array.isArray(v)) return v.length ? v.join(", ") : "(kosong)";
  if (v && typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** Panel "Aturan Bisnis" — semua angka kebijakan bisa diubah tanpa deploy (Fase 39). */
export default function SettingsPanel() {
  const { labelOf } = useReference();
  // Fase 41: kelompok bisa ditaut dari luar (`/config?group=sla`) — tautan "Ubah SLA" di
  // laporan Umur Tahap harus mendarat pada kelompok yang dimaksud, bukan daftar penuh.
  const [params, setParams] = useSearchParams();
  const [rows, setRows] = useState([]);
  const [groups, setGroups] = useState([]);
  const [group, setGroup] = useState(params.get("group") || "");
  const [query, setQuery] = useState({ q: "", sort: "key", direction: "asc", skip: 0, limit: 50 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState({});
  const [confirm, setConfirm] = useState(null);
  const [reason, setReason] = useState("");
  const [history, setHistory] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/settings", { params: { group: group || undefined, q: query.q || undefined } });
      setRows(res.data.data || []);
      setGroups(res.data.groups || []);
      setDraft({});
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat konfigurasi.");
    } finally { setLoading(false); }
  }, [group, query.q]);

  useEffect(() => { load(); }, [load]);

  const save = async (row, value, why) => {
    try {
      await api.put(`/settings/${row.key}`, { value, reason: why || undefined });
      toast.success(`"${row.label}" diperbarui.`);
      setConfirm(null); setReason("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan konfigurasi.");
    }
  };

  const requestSave = (row) => {
    const value = draft[row.key] !== undefined ? draft[row.key] : row.value;
    if (row.sensitive) { setConfirm({ row, value }); return; }
    save(row, value);
  };

  const reset = async (row) => {
    try {
      await api.post(`/settings/${row.key}/reset`);
      toast.success(`"${row.label}" dikembalikan ke bawaan sistem.`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengembalikan nilai.");
    }
  };

  const openHistory = async (row) => {
    try {
      const res = await api.get(`/settings/${row.key}/history`);
      setHistory({ row, items: res.data.data || [] });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memuat riwayat.");
    }
  };

  const editor = (row) => {
    const val = draft[row.key] !== undefined ? draft[row.key] : row.value;
    const set = (v) => setDraft((d) => ({ ...d, [row.key]: v }));
    if (row.type === "bool") {
      return (
        <Switch data-testid={CONFIG.ruleSwitch} checked={!!val}
          aria-label={row.label} onCheckedChange={(v) => set(v)} />
      );
    }
    if (row.type === "enum") {
      return (
        <Select value={String(val)} onValueChange={set}>
          <SelectTrigger data-testid={CONFIG.ruleSelect} className="h-8 w-full"
            aria-label={row.label}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(row.options || []).map((o) => (
              <SelectItem key={o} value={o} data-testid={`config-enum-option-${o}`}>
                {row.option_labels?.[o] || labelOf(row.ref_group, o)}
                <span className="ml-1.5 font-mono text-[10px] text-muted-foreground">{o}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    }
    if (row.type === "list") {
      if (Array.isArray(val) && val.some((x) => x && typeof x === "object")) {
        return <span className="text-xs text-muted-foreground" data-testid={CONFIG.ruleInput}>Disunting lewat tab khusus (mis. Skor Lead) — {val.length} baris.</span>;
      }
      return (
        <Input data-testid={CONFIG.ruleInput} className="h-8 bg-background"
          aria-label={row.label} value={Array.isArray(val) ? val.join(", ") : String(val || "")}
          onChange={(e) => set(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
      );
    }
    if (row.type === "obj") {
      const isMap = val && typeof val === "object" && !Array.isArray(val);
      // Kebijakan SLA per tahap adalah objek yang SERING diubah pemilik. Menyuruh orang
      // mengetik JSON untuk itu = mengundang salah ketik yang langsung berakibat pada
      // angka "lewat SLA" di semua daftar. Karena itu peta angka disajikan sebagai kolom
      // input per tahap (JSON tetap tersedia untuk objek bentuk lain).
      if (isMap && Object.values(val).every((v) => typeof v === "number")) {
        return (
          <div className="grid gap-1.5 sm:grid-cols-2">
            {Object.keys(val).map((stage) => (
              <label key={stage} className="flex items-center gap-1.5 text-xs">
                <span className="w-28 shrink-0 truncate text-muted-foreground" title={stage}>
                  {stage}
                </span>
                <Input data-testid={`${CONFIG.ruleInput}-${row.key}-${stage}`} type="number"
                  step="0.25" min="0" className="h-8 bg-background"
                  aria-label={`${row.label} — ${stage}`} value={val[stage]}
                  onChange={(e) => set({
                    ...val,
                    [stage]: e.target.value === "" ? 0 : Number(e.target.value),
                  })} />
              </label>
            ))}
          </div>
        );
      }
      return (
        <Textarea data-testid={CONFIG.ruleInput} rows={2} aria-label={row.label}
          className="bg-background font-mono text-xs"
          value={typeof val === "string" ? val : JSON.stringify(val)}
          onChange={(e) => {
            try { set(JSON.parse(e.target.value)); } catch { set(e.target.value); }
          }} />
      );
    }
    if (/\(Rp\b|\bRp\b|rupiah/i.test(row.label || "")) {
      return (
        <RupiahInput data-testid={CONFIG.ruleInput} className="h-8 bg-background"
          aria-label={row.label} value={val ?? ""}
          onChange={(e) => set(e.target.value === "" ? "" : Number(e.target.value))} />
      );
    }
    if (!["int", "float", "number", "money", "pct"].includes(row.type)) {
      const inputType = /^\d{2}:\d{2}$/.test(String(row.value || "")) ? "time" : "text";
      return <Input data-testid={`${CONFIG.ruleInput}-${row.key}`} type={inputType}
        className="h-8 bg-background" aria-label={row.label} value={val ?? ""}
        onChange={e => set(e.target.value)} />;
    }
    return (
      <Input data-testid={CONFIG.ruleInput} type="number" className="h-8 bg-background"
        aria-label={row.label} value={val ?? ""}
        onChange={(e) => set(e.target.value === "" ? "" : Number(e.target.value))} />
    );
  };

  const columns = useMemo(() => [
    {
      key: "label", header: "Aturan", sortable: true,
      render: (r) => (
        <div className="min-w-[240px] space-y-0.5">
          <div className="font-medium">{r.label}</div>
          <div className="text-xs text-muted-foreground">{r.help}</div>
          {r.impact ? (
            <div className="text-xs text-amber-700">Dampak: {r.impact}</div>
          ) : null}
          <div className="font-mono text-[10px] text-muted-foreground">{r.key}</div>
        </div>
      ),
      exportValue: (r) => r.label,
    },
    { key: "group_label", header: "Kelompok", sortable: true },
    {
      key: "value", header: "Nilai berlaku", width: 210,
      render: (r) => <div className="space-y-1">{editor(r)}
        <div className="text-[10px] text-muted-foreground">Saat ini: {valueText(r)}</div>
      </div>,
      exportValue: (r) => valueText(r),
    },
    {
      key: "origin", header: "Asal nilai", sortable: true,
      render: (r) => (
        <div className="space-y-0.5 text-xs">
          <div>{labelOf("setting_origin", r.origin)}</div>
          <div className="text-muted-foreground">Dasar: {labelOf("setting_source", r.source)}</div>
          {r.updated_by ? (
            <div className="text-muted-foreground">{r.updated_by} · {formatDateTimeWIB(r.updated_at)}</div>
          ) : null}
        </div>
      ),
      exportValue: (r) => r.origin,
    },
    {
      key: "actions", header: "Aksi", align: "right", sticky: true,
      render: (r) => (
        <div className="flex justify-end gap-1">
          <Button data-testid={CONFIG.ruleSave} size="sm" variant="secondary"
            disabled={draft[r.key] === undefined} onClick={() => requestSave(r)}>
            <Save className="mr-1 h-3.5 w-3.5" /> Simpan
          </Button>
          <Button data-testid={CONFIG.ruleHistory} size="sm" variant="ghost"
            onClick={() => openHistory(r)} title="Riwayat perubahan">
            <History className="h-3.5 w-3.5" />
          </Button>
          <Button data-testid={CONFIG.ruleReset} size="sm" variant="ghost"
            disabled={r.origin === "default"} onClick={() => reset(r)} title="Kembalikan bawaan">
            <RotateCcw className="h-3.5 w-3.5" />
          </Button>
        </div>
      ),
      exportValue: () => "",
    },
  ], [draft, rows]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div data-testid={CONFIG.rulesPanel} className="space-y-3">
      <div className="rounded-md border bg-secondary p-3 text-sm">
        Semua aturan bisnis (masa keep unit, DP, potongan pembatalan, toleransi cicilan, tarif
        pajak mitra, penomoran dokumen) dibaca dari sini — <strong>tidak ada angka mati di
        kode</strong>. Perubahan pada aturan sensitif wajib beralasan dan selalu tercatat.
      </div>
      <DataTable
        testId="config-settings-table"
        testIds={{ search: CONFIG.rulesSearch, row: CONFIG.rulesRow, export: "config-rules-export",
          columns: "config-rules-columns", pagination: "config-rules-pagination" }}
        columns={columns} rows={rows} total={rows.length} query={query}
        onQueryChange={(p) => setQuery((q) => ({ ...q, ...p }))}
        loading={loading} error={error} onRefresh={load}
        searchPlaceholder="Cari aturan (mis. booking, cicilan, pajak)…"
        exportName="aturan-bisnis" emptyTitle="Tidak ada aturan yang cocok"
        filters={(
          <Select value={group || "__all__"}
            onValueChange={(v) => {
              const next = v === "__all__" ? "" : v;
              setGroup(next);
              // Kelompok yang dipilih ikut hidup di URL supaya bisa dibagikan/di-bookmark.
              const p = new URLSearchParams(params);
              if (next) p.set("group", next); else p.delete("group");
              setParams(p, { replace: true });
            }}>
            <SelectTrigger data-testid={CONFIG.rulesGroup} className="h-9 w-[220px]"
              aria-label="Kelompok aturan">
              <SelectValue placeholder="Semua kelompok" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">Semua kelompok</SelectItem>
              {groups.map((g) => (
                <SelectItem key={g.group} value={g.group}>
                  {g.label} ({g.overridden}/{g.total} diubah)
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      />

      <Dialog open={!!confirm} onOpenChange={(o) => { if (!o) { setConfirm(null); setReason(""); } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ubah aturan sensitif</DialogTitle>
            <DialogDescription>
              {confirm?.row?.label} — {confirm?.row?.impact || "Perubahan ini memengaruhi proses bisnis."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="rule-reason">Alasan perubahan (wajib)</Label>
            <Textarea id="rule-reason" data-testid={CONFIG.ruleReason} rows={3}
              placeholder="Contoh: kebijakan baru direksi per Agustus 2026"
              value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => { setConfirm(null); setReason(""); }}>Batal</Button>
            <Button data-testid={CONFIG.ruleReasonSubmit} disabled={!reason.trim()}
              onClick={() => save(confirm.row, confirm.value, reason)}>
              Simpan perubahan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!history} onOpenChange={(o) => { if (!o) setHistory(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Riwayat: {history?.row?.label}</DialogTitle>
            <DialogDescription>Setiap perubahan menyimpan aktor, waktu, dan alasan.</DialogDescription>
          </DialogHeader>
          <div className="max-h-[50vh] space-y-2 overflow-y-auto">
            {(history?.items || []).length ? history.items.map((h, i) => (
              <div key={i} className="rounded-md border bg-card p-2 text-sm shadow-[var(--shadow-card)]">
                <div className="font-medium">{String(h.from)} → {String(h.to)}</div>
                <div className="text-xs text-muted-foreground">
                  {h.by} · {formatDateTimeWIB(h.at)} · {h.scope}
                </div>
                {h.reason ? <div className="text-xs">Alasan: {h.reason}</div> : null}
              </div>
            )) : (
              <p className="text-sm text-muted-foreground">Belum pernah diubah dari bawaan sistem.</p>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
