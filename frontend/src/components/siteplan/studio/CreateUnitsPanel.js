import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Sparkles, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import api from "@/services/apiClient";
import { STUDIO } from "@/constants/testIds";

/**
 * Lahirkan unit dari kavling yang belum terpetakan: blok & nomor dibaca dari label gambar
 * (bisa dikoreksi), tipe unit dipilih, blok baru dibuat hanya bila diizinkan.
 */
export default function CreateUnitsPanel({ s }) {
  const [rows, setRows] = useState([]);
  const [typeCode, setTypeCode] = useState("");
  const [clusterId, setClusterId] = useState("");
  const [allowBlocks, setAllowBlocks] = useState(false);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await api.get(`/site-plan-studio/${s.projectId}/suggest-units`);
      setRows((res.data.data || []).map((r) => ({ ...r, checked: !r.existing_unit_id || true,
        block_code: r.block_code || "", no: r.no || "" })));
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memuat usulan."); }
  }, [s.projectId]);

  useEffect(() => { load(); }, [load, s.plan?.updated_at]);
  useEffect(() => { if (!typeCode && s.data?.unit_types?.[0]) setTypeCode(s.data.unit_types[0].code); }, [s.data, typeCode]);

  const set = (sid, patch) => setRows((rs) => rs.map((r) => (r.shape_id === sid ? { ...r, ...patch } : r)));
  const picked = rows.filter((r) => r.checked && r.block_code && r.no);
  const newBlocks = [...new Set(picked.filter((r) => !s.data?.blocks?.some((b) => b.code === r.block_code.toUpperCase())).map((r) => r.block_code.toUpperCase()))];

  const submit = async () => {
    setBusy(true); setResult(null);
    try {
      const res = await api.post(`/site-plan-studio/${s.projectId}/create-units`, {
        items: picked.map((r) => ({ shape_id: r.shape_id, block_code: r.block_code, no: r.no })),
        create_blocks: allowBlocks, cluster_id: clusterId || null, unit_type_code: typeCode || null,
      });
      setResult(res.data.data);
      toast.success(`${res.data.data.created} unit dibuat, ${res.data.data.mapped} kavling terpetakan${res.data.data.failed ? `, ${res.data.data.failed} gagal` : ""}.`);
      await s.load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat unit."); } finally { setBusy(false); }
  };

  if (!s.plan) return <p className="text-sm text-muted-foreground">Unggah SVG/gambar dahulu.</p>;
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        {rows.length} kavling belum punya unit. Blok & nomor dibaca dari label gambar — koreksi bila perlu.
        Kavling yang kodenya sudah ada di database akan <strong>dipetakan</strong> ke unit itu (tidak digandakan).
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        <div className="space-y-1">
          <Label>Tipe unit (untuk unit baru)</Label>
          <Select value={typeCode} onValueChange={setTypeCode}>
            <SelectTrigger data-testid={STUDIO.createType} aria-label="Tipe unit"><SelectValue placeholder="Pilih tipe" /></SelectTrigger>
            <SelectContent>{(s.data?.unit_types || []).map((t) => <SelectItem key={t.code} value={t.code}>{t.code} · {t.name}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>Cluster untuk blok baru</Label>
          <Select value={clusterId || "__default"} onValueChange={(v) => setClusterId(v === "__default" ? "" : v)}>
            <SelectTrigger aria-label="Cluster"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__default">Cluster utama (otomatis)</SelectItem>
              {(s.data?.clusters || []).map((c) => <SelectItem key={c.id} value={c.id}>{c.code} · {c.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>
      <label className="flex items-start gap-2 rounded-md border bg-amber-50/60 p-2 text-xs">
        <Checkbox data-testid={STUDIO.createAllowBlocks} checked={allowBlocks} onCheckedChange={(v) => setAllowBlocks(!!v)} className="mt-0.5" />
        <span>
          Izinkan membuat <strong>blok baru</strong> bila belum ada
          {newBlocks.length ? <> — akan dibuat: <span className="font-mono">{newBlocks.join(", ")}</span></> : null}.
          Tanpa centang, baris berblok baru dilaporkan gagal (tidak menghentikan baris lain).
        </span>
      </label>
      <div className="max-h-[38vh] space-y-1 overflow-y-auto pr-1">
        {rows.map((r) => {
          const blockOk = s.data?.blocks?.some((b) => b.code === (r.block_code || "").toUpperCase());
          return (
            <div key={r.shape_id} data-testid={STUDIO.createRow}
              className={`grid grid-cols-[auto_1fr_1fr_1fr] items-center gap-1.5 rounded-md border px-2 py-1 text-xs ${s.selectedId === r.shape_id ? "border-blue-400" : ""}`}
              onClick={() => s.setSelectedId(r.shape_id)}>
              <Checkbox checked={r.checked} onCheckedChange={(v) => set(r.shape_id, { checked: !!v })} aria-label="Sertakan" />
              <span className="truncate font-mono" title={r.label || r.shape_id}>{r.label || <span className="text-muted-foreground">tanpa label</span>}</span>
              <Input data-testid={STUDIO.createBlock} value={r.block_code} placeholder="Blok" aria-label="Blok"
                className={`h-7 font-mono ${r.block_code && !blockOk ? "border-amber-400" : ""}`}
                onChange={(e) => set(r.shape_id, { block_code: e.target.value.toUpperCase() })} />
              <div className="flex items-center gap-1">
                <Input data-testid={STUDIO.createNo} value={r.no} placeholder="No" aria-label="Nomor" className="h-7 font-mono"
                  onChange={(e) => set(r.shape_id, { no: e.target.value })} />
                {r.existing_unit_id ? <span title={`Unit ${r.existing_unit_code} sudah ada → dipetakan`} className="text-emerald-600">↺</span> : null}
              </div>
            </div>
          );
        })}
        {!rows.length ? <p className="rounded-md border border-dashed p-3 text-center text-xs text-muted-foreground">Semua kavling di peta sudah punya unit.</p> : null}
      </div>
      <Button data-testid={STUDIO.createSubmit} disabled={!picked.length || busy} onClick={submit} className="w-full">
        <Sparkles className="mr-1.5 h-4 w-4" /> {busy ? "Memproses…" : `Buat / petakan ${picked.length} unit`}
      </Button>
      {result ? (
        <div data-testid={STUDIO.createResult} className="max-h-40 space-y-1 overflow-y-auto rounded-md border p-2 text-xs">
          {result.results.map((r) => (
            <div key={r.shape_id} className="flex items-center gap-1.5">
              {r.ok ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> : <XCircle className="h-3.5 w-3.5 text-red-600" />}
              <span className="font-mono">{r.code || r.shape_id}</span>
              <span className="text-muted-foreground">{r.ok ? (r.reused ? "dipetakan ke unit yang ada" : `unit baru${r.block_created ? " + blok baru" : ""}`) : r.error}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
