import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, ShieldCheck, Trash2 } from "lucide-react";

import api from "@/services/apiClient";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatNumber } from "@/utils/formatters";
import { DATAMGMT } from "@/constants/testIds";
import { errDetail } from "./dataMgmtUtils";

const ORDER = ["transaksi", "proyek", "mitra"];

/** Hapus massal data operasional (konfigurasi & master sistem dipertahankan). */
export default function PurgePanel({ onChanged }) {
  const [data, setData] = useState(null);
  const [picked, setPicked] = useState({ transaksi: true, proyek: true, mitra: true });
  const [confirm, setConfirm] = useState("");
  const [snapshot, setSnapshot] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await api.get("/data-mgmt/purge/preview");
      setData(res.data);
    } catch (e) { toast.error(errDetail(e, "Gagal memuat ringkasan data.")); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const groups = ORDER.filter((k) => picked[k]);
  const total = groups.reduce((s, k) => s + (data?.groups?.[k]?.total || 0), 0);

  const run = async () => {
    setBusy(true);
    try {
      const res = await api.post("/data-mgmt/purge", { groups, confirm, snapshot });
      setResult(res.data);
      setConfirm("");
      toast.success(`${formatNumber(res.data.deleted)} dokumen dihapus.`);
      load(); onChanged?.();
    } catch (e) { toast.error(errDetail(e, "Gagal menghapus data.")); } finally { setBusy(false); }
  };

  return (
    <div data-testid={DATAMGMT.purgePanel} className="grid gap-6 lg:grid-cols-2">
      <div className="rounded-xl border bg-card p-5 space-y-4 shadow-[var(--shadow-card)]">
        <div className="flex items-start justify-between">
          <div><p className="eyebrow">Hapus massal</p><h3 className="font-semibold">Bersihkan data operasional</h3></div>
          <Trash2 className="h-7 w-7 text-destructive" />
        </div>
        <div className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>Permanen. Pengguna, hak akses, bagan akun, skema, template, dan pengaturan lain <b>tidak</b> disentuh.
            Setelah dihapus, data contoh (demo) tidak akan dibuat ulang saat aplikasi dimulai.</span>
        </div>

        <div className="space-y-3">
          {ORDER.map((k) => {
            const g = data?.groups?.[k];
            return (
              <label key={k} data-testid={`${DATAMGMT.purgeGroup}-${k}`}
                className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 hover:bg-accent/40 transition-colors">
                <Checkbox data-testid={`${DATAMGMT.purgeGroupCheck}-${k}`} checked={!!picked[k]}
                  onCheckedChange={(v) => setPicked({ ...picked, [k]: !!v })} className="mt-0.5" />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-medium">{g?.label || k}</span>
                    <span data-testid={`${DATAMGMT.purgeGroupTotal}-${k}`} className="text-xs tabular-nums text-muted-foreground">
                      {g ? `${formatNumber(g.total)} dok.` : "…"}
                    </span>
                  </span>
                  <span className="block text-xs text-muted-foreground">{g?.help}</span>
                </span>
              </label>
            );
          })}
        </div>

        <label className="flex items-center gap-2 text-sm">
          <Checkbox data-testid={DATAMGMT.purgeSnapshot} checked={snapshot} onCheckedChange={(v) => setSnapshot(!!v)} />
          Buat snapshot pengaman dulu (bisa di-restore dari tab Backup)
        </label>

        <div className="space-y-1.5">
          <Label htmlFor="purge-confirm">Ketik <b>HAPUS</b> untuk mengonfirmasi</Label>
          <Input id="purge-confirm" data-testid={DATAMGMT.purgeConfirm} value={confirm}
            onChange={(e) => setConfirm(e.target.value)} placeholder="HAPUS" autoComplete="off" />
        </div>
        <Button variant="destructive" data-testid={DATAMGMT.purgeSubmit}
          disabled={busy || !groups.length || confirm.trim().toUpperCase() !== "HAPUS"} onClick={run}>
          <Trash2 className="h-4 w-4 mr-2" />
          {busy ? "Menghapus…" : `Hapus ${formatNumber(total)} dokumen`}
        </Button>
      </div>

      <div className="space-y-4">
        {result ? (
          <div data-testid={DATAMGMT.purgeResult} className="rounded-xl border border-emerald-300 bg-emerald-50 p-5 text-sm text-emerald-900">
            <p className="flex items-center gap-2 font-semibold"><ShieldCheck className="h-4 w-4" /> Selesai — {formatNumber(result.deleted)} dokumen dihapus</p>
            <ul className="mt-2 grid grid-cols-2 gap-x-4 text-xs">
              {Object.entries(result.collections || {}).map(([c, n]) => (
                <li key={c} className="flex justify-between"><span>{c}</span><span className="tabular-nums">{formatNumber(n)}</span></li>
              ))}
            </ul>
            {result.snapshot_before ? <p className="mt-2 text-xs">Snapshot pengaman: <b>{result.snapshot_before.filename}</b></p> : null}
          </div>
        ) : null}
        <div className="rounded-xl border bg-card p-5 shadow-[var(--shadow-card)]">
          <p className="eyebrow">Dipertahankan</p>
          <h3 className="font-semibold">Konfigurasi & master sistem</h3>
          <p className="mt-1 text-xs text-muted-foreground">Koleksi berikut tidak pernah ikut terhapus:</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {(data?.keep || []).map((c) => (
              <span key={c} className="rounded-full bg-secondary px-2 py-0.5 font-mono text-[11px]">{c}</span>
            ))}
          </div>
          {data?.demo_seed_disabled ? (
            <p data-testid={DATAMGMT.purgeSeedFlag} className="mt-3 text-xs text-emerald-700">Seed data demo sudah dimatikan untuk organisasi ini.</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
