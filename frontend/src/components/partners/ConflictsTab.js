import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Scale } from "lucide-react";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { fromNow } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PARTNERS } from "@/constants/testIds";

/**
 * ConflictsTab — **Sengketa Atribusi** (Fase 42 §5.3).
 *
 * Kejadian nyata di bisnis agen: satu calon pembeli dikirim dua mitra. Kalau tidak diputuskan
 * dengan aturan, dua mitra akan menagih fee atas satu pembeli. Sistem memutuskan otomatis
 * memakai model atribusi di Pusat Konfigurasi (`partner.attribution_model`) dan MENCATAT
 * sengketanya; bila modelnya `manual_review`, keputusan menunggu manusia — di layar ini.
 */
export default function ConflictsTab() {
  const { can } = useAuth();
  // Izin diambil dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis
  // ulang di layar. Matriks RBAC bisa diubah admin lewat Pusat Konfigurasi; daftar peran
  // hardcode membuat tombol berbeda dengan jawaban server — tombol mati (403) atau
  // tombol yang seharusnya ada tapi hilang.
  const canDecide = can("partners", "update");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [decideFor, setDecideFor] = useState(null);
  const [choice, setChoice] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/partners/conflicts");
      setRows(res.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat sengketa atribusi.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    if (!choice) { toast.error("Pilih mitra yang berhak."); return; }
    if (reason.trim().length < 5) { toast.error("Alasan keputusan wajib diisi."); return; }
    setBusy(true);
    try {
      await api.post(`/partners/conflicts/${decideFor.id}/decide`, {
        partner_id: choice, reason: reason.trim(),
      });
      toast.success("Keputusan disimpan — lead dipindahkan ke mitra yang berhak.");
      setDecideFor(null); setChoice(""); setReason("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan keputusan.");
    } finally { setBusy(false); }
  };

  if (loading && !rows.length) return <LoadingCards count={2} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Satu nomor diklaim lebih dari satu mitra dalam jendela dedup. Model atribusi &amp;
        panjang jendela diatur di Pusat Konfigurasi (kelompok Mitra).
      </p>

      {rows.length === 0 ? (
        <EmptyState icon={Scale} title="Tidak ada sengketa atribusi"
          description="Belum ada nomor yang diklaim lebih dari satu mitra." />
      ) : (
        <div className="overflow-x-auto rounded-lg border bg-card shadow-[var(--shadow-card)]">
          <table data-testid={PARTNERS.conflictsTable} className="w-full text-sm">
            <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Nomor</th>
                <th className="px-3 py-2 text-left">Pemegang (lebih dulu)</th>
                <th className="px-3 py-2 text-left">Pengklaim</th>
                <th className="px-3 py-2 text-left">Model</th>
                <th className="px-3 py-2 text-left">Keputusan</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-left">Waktu</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} data-testid={PARTNERS.conflictRow} data-conflict={c.id}
                  className="border-t">
                  <td className="px-3 py-2 font-medium">{c.phone}</td>
                  <td className="px-3 py-2">{c.held_by_name || "—"}</td>
                  <td className="px-3 py-2">{c.claimed_by_name || "—"}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {c.model} · {c.window_days} hari
                  </td>
                  <td className="px-3 py-2">
                    {c.decision_name || <span className="text-muted-foreground">menunggu</span>}
                    {c.decision_reason ? (
                      <p className="text-xs text-muted-foreground">{c.decision_reason}</p>
                    ) : null}
                  </td>
                  <td className="px-3 py-2">
                    <StatusPill status={c.status} group="partner_conflict_status" />
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {fromNow(c.created_at)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {canDecide ? (
                      <Button size="sm" variant="outline" data-testid={PARTNERS.conflictDecide}
                        data-conflict={c.id}
                        aria-label={`Putuskan sengketa nomor ${c.phone}`}
                        onClick={() => { setDecideFor(c); setChoice(c.decision || ""); }}>
                        Putuskan
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={!!decideFor} onOpenChange={(v) => !v && setDecideFor(null)}>
        <DialogContent data-testid={PARTNERS.conflictDialog}>
          <DialogHeader>
            <DialogTitle>Putuskan Sengketa Atribusi</DialogTitle>
            <DialogDescription>
              Nomor {decideFor?.phone}. Lead akan dipindahkan ke mitra yang dipilih, dan
              keputusan ini tercatat pada riwayat mitra.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>Mitra yang berhak</Label>
              <Select value={choice} onValueChange={setChoice}>
                <SelectTrigger data-testid={PARTNERS.conflictChoice} aria-label="Mitra berhak">
                  <SelectValue placeholder="Pilih mitra" />
                </SelectTrigger>
                <SelectContent>
                  {decideFor?.held_by ? (
                    <SelectItem value={decideFor.held_by}>
                      {decideFor.held_by_name} (pemegang lebih dulu)
                    </SelectItem>
                  ) : null}
                  {decideFor?.claimed_by ? (
                    <SelectItem value={decideFor.claimed_by}>
                      {decideFor.claimed_by_name} (pengklaim)
                    </SelectItem>
                  ) : null}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="creason">Alasan keputusan (wajib)</Label>
              <Textarea id="creason" rows={3} data-testid={PARTNERS.conflictReason}
                value={reason} onChange={(e) => setReason(e.target.value)}
                placeholder="Mis. bukti percakapan pertama ada di mitra A pada 3 Agustus…" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDecideFor(null)} disabled={busy}>
              Batal
            </Button>
            <Button data-testid={PARTNERS.conflictSubmit} onClick={submit} disabled={busy}>
              {busy ? "Menyimpan…" : "Simpan Keputusan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
