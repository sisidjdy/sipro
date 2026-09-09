import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { MapPin, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { MASTER } from "@/constants/testIds";

/**
 * KEBIJAKAN BUKTI KERJA (admin) — satu tempat mengatur seberapa ketat bukti pekerjaan
 * konstruksi, dan aturannya langsung berlaku di semua jalur pengajuan (Papan Mandor,
 * sheet jadwal unit, maupun API).
 *
 * Sengaja dipisah dari template jadwal: template mengatur APA yang dikerjakan, kebijakan
 * ini mengatur SEBERAPA KUAT buktinya. Perekaman lokasi bisa dimatikan karena menyangkut
 * privasi pekerja dan tidak semua lokasi punya sinyal GPS bagus.
 */
export default function BuildPolicyPanel() {
  const [pol, setPol] = useState(null);
  const [canEdit, setCanEdit] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const r = await api.get("/build/policy");
      setPol(r.data?.data || {});
      setCanEdit(!!r.data?.can_edit);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat kebijakan bukti kerja.");
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const save = async () => {
    setBusy(true);
    try {
      const r = await api.put("/build/policy", {
        geo_required: !!pol.geo_required,
        camera_only: !!pol.camera_only,
        min_note_chars: Number(pol.min_note_chars) || 10,
        min_accuracy_m: Number(pol.min_accuracy_m) || 200,
      });
      setPol(r.data?.data || pol);
      toast.success(r.data?.message || "Kebijakan bukti kerja disimpan.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan kebijakan.");
    } finally { setBusy(false); }
  };

  if (loading) return <LoadingCards count={1} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!pol) return null;

  return (
    <div data-testid={MASTER.buildPolicyPanel} className="space-y-4">
      <div className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
        <p className="inline-flex items-center gap-1.5 font-heading text-base font-semibold">
          <ShieldCheck className="h-4 w-4 text-primary" /> Kebijakan bukti kerja konstruksi
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Berlaku untuk semua pengajuan hasil pekerjaan unit. Perubahan langsung dipakai
          Papan Mandor dan tercatat pada jejak audit tiap pengajuan.
        </p>
        {!canEdit ? (
          <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-[11px] text-amber-900">
            Hanya Direksi/Super Admin yang boleh mengubah kebijakan ini — Anda bisa melihat
            aturan yang berlaku sekarang.
          </p>
        ) : null}

        <div className="mt-4 space-y-3">
          <Row title="Wajib merekam lokasi (GPS) saat mengajukan hasil"
            desc={"Koordinat diminta dari HP saat pengajuan dan disimpan pada bukti. "
              + "Metadata EXIF/GPS pada berkas foto tetap dibuang demi privasi pembeli."}>
            <Switch data-testid={MASTER.policyGeo} checked={!!pol.geo_required}
              disabled={!canEdit}
              onCheckedChange={(v) => setPol({ ...pol, geo_required: v })} />
          </Row>
          <Row title="Hanya boleh dari kamera (bukan galeri)"
            desc={"Tombol utama pengambilan foto membuka kamera langsung. Berguna untuk "
              + "mengurangi foto lama yang diunggah ulang."}>
            <Switch data-testid={MASTER.policyCamera} checked={!!pol.camera_only}
              disabled={!canEdit}
              onCheckedChange={(v) => setPol({ ...pol, camera_only: v })} />
          </Row>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="minnote">Panjang minimal uraian pekerjaan (karakter)</Label>
              <Input id="minnote" type="number" min={5} max={200}
                data-testid={MASTER.policyNoteChars} disabled={!canEdit}
                value={pol.min_note_chars ?? 10}
                onChange={(e) => setPol({ ...pol, min_note_chars: e.target.value })} />
              <p className="text-[11px] text-muted-foreground">
                Mencegah uraian “selesai” tanpa isi.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="minacc">Akurasi lokasi maksimal yang diterima (meter)</Label>
              <Input id="minacc" type="number" min={10} max={5000}
                data-testid={MASTER.policyAccuracy} disabled={!canEdit}
                value={pol.min_accuracy_m ?? 200}
                onChange={(e) => setPol({ ...pol, min_accuracy_m: e.target.value })} />
              <p className="text-[11px] text-muted-foreground">
                Hanya berlaku bila perekaman lokasi diwajibkan.
              </p>
            </div>
          </div>
        </div>

        {canEdit ? (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
            <p className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <MapPin className="h-3.5 w-3.5" />
              {pol.updated_by ? `Terakhir diubah ${pol.updated_by}` : "Belum pernah diubah"}
              {pol.updated_at ? ` · ${String(pol.updated_at).slice(0, 10)}` : ""}
            </p>
            <Button size="sm" data-testid={MASTER.policySave} onClick={save} disabled={busy}>
              {busy ? "Menyimpan…" : "Simpan kebijakan"}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Row({ title, desc, children }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 rounded-lg border bg-background p-3">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{title}</p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">{desc}</p>
      </div>
      {children}
    </div>
  );
}
