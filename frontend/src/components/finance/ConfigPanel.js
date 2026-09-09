import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Trash2, Plus, Star , Pencil} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { PaymentSchemeDialog, CommissionSchemeDialog } from "@/components/finance/SchemeDialogs";
import { formatIDR } from "@/utils/formatters";
import RenameSchemeDialog from "@/components/finance/RenameSchemeDialog";
import ConfirmDialog from "@/components/patterns/ConfirmDialog";
import { useReference } from "@/context/ReferenceContext";
import api from "@/services/apiClient";
import { FINANCE } from "@/constants/testIds";

export default function ConfigPanel() {
  const { labelOf } = useReference();
  const [tax, setTax] = useState(null);
  const [paySchemes, setPaySchemes] = useState([]);
  const [comSchemes, setComSchemes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [payOpen, setPayOpen] = useState(false);
  const [comOpen, setComOpen] = useState(false);
  const [editScheme, setEditScheme] = useState(null);
  const [delScheme_, setDelScheme_] = useState(null);
  const [collectionCfg, setCollectionCfg] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [t, ps, cs, col] = await Promise.all([
        api.get("/finance/config/tax"),
        api.get("/finance/config/payment-schemes"),
        api.get("/finance/config/commission-schemes"),
        api.get("/finance/config/collection"),
      ]);
      setTax(t.data.data);
      setPaySchemes(ps.data.data || []);
      setComSchemes(cs.data.data || []);
      setCollectionCfg(col.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat konfigurasi keuangan.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const saveTax = async () => {
    setBusy(true);
    try {
      await api.put("/finance/config/tax", {
        ppn_rate: Number(tax.ppn_rate) || 0,
        bphtb_rate: Number(tax.bphtb_rate) || 0,
        pph_rate: Number(tax.pph_rate) || 0,
        npoptkp: Number(tax.npoptkp) || 0,
      });
      toast.success("Konfigurasi pajak disimpan.");
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan pajak."); }
    finally { setBusy(false); }
  };

  const saveCollection = async () => {
    setBusy(true);
    try {
      const res = await api.put("/finance/config/collection", {
        denda_rate_pct_month: Number(collectionCfg.denda_rate_pct_month) || 0,
        grace_days: Number(collectionCfg.grace_days) || 0,
      });
      setCollectionCfg(res.data.data);
      toast.success("Konfigurasi penagihan disimpan.");
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan konfigurasi penagihan."); }
    finally { setBusy(false); }
  };

  const setC = (k, v) => setCollectionCfg((prev) => ({ ...prev, [k]: v }));

  const delScheme = async () => {
    const target = delScheme_;
    if (!target) return;
    setBusy(true);
    try {
      if (target.kind === "payment-schemes") {
        await api.delete(`/finance/config/payment-schemes/${target.scheme.id}`);
      } else {
        await api.delete(`/finance/config/commission-schemes/${target.scheme.id}`);
      }
      toast.success(`Skema “${target.scheme.name}” dihapus.`);
      setDelScheme_(null);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menghapus skema."); }
    finally { setBusy(false); }
  };

  if (loading) return <LoadingCards count={4} />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!tax) return null;

  const setT = (k, v) => setTax((prev) => ({ ...prev, [k]: v }));

  return (
    <div data-testid={FINANCE.configPanel} className="space-y-6">
      {/* Tax config */}
      <section className="rounded-xl border bg-card p-4 shadow-sm">
        <h3 className="font-heading text-sm font-semibold">Konfigurasi Pajak</h3>
        <p className="text-[11px] text-muted-foreground">Nilai acuan — wajib dikonfirmasi penasihat pajak saat go-live.</p>
        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="space-y-1.5">
            <Label htmlFor="ppn">PPN (%)</Label>
            <Input id="ppn" type="number" value={tax.ppn_rate ?? ""} data-testid="tax-ppn"
              onChange={(e) => setT("ppn_rate", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bphtb">BPHTB (%)</Label>
            <Input id="bphtb" type="number" value={tax.bphtb_rate ?? ""} data-testid="tax-bphtb"
              onChange={(e) => setT("bphtb_rate", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pph">PPh Final (%)</Label>
            <Input id="pph" type="number" value={tax.pph_rate ?? ""} data-testid="tax-pph"
              onChange={(e) => setT("pph_rate", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="npoptkp">NPOPTKP (Rp)</Label>
            <RupiahInput id="npoptkp" value={tax.npoptkp ?? ""} data-testid="tax-npoptkp"
              onChange={(e) => setT("npoptkp", e.target.value)} />
          </div>
        </div>
        <div className="mt-3 flex justify-end">
          <Button data-testid={FINANCE.taxSubmit} onClick={saveTax} disabled={busy}>
            {busy ? "Menyimpan\u2026" : "Simpan Pajak"}
          </Button>
        </div>
      </section>

      {/* Collection config (denda + masa tenggang) */}
      {collectionCfg ? (
        <section className="rounded-xl border bg-card p-4 shadow-sm">
          <h3 className="font-heading text-sm font-semibold">Konfigurasi Penagihan</h3>
          <p className="text-[11px] text-muted-foreground">Denda keterlambatan (per bulan) & masa tenggang sebelum denda berlaku.</p>
          <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="space-y-1.5">
              <Label htmlFor="denda">Denda (%/bulan)</Label>
              <Input id="denda" type="number" value={collectionCfg.denda_rate_pct_month ?? ""} data-testid="collection-denda-rate"
                onChange={(e) => setC("denda_rate_pct_month", e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="grace">Masa Tenggang (hari)</Label>
              <Input id="grace" type="number" value={collectionCfg.grace_days ?? ""} data-testid="collection-grace-days"
                onChange={(e) => setC("grace_days", e.target.value)} />
            </div>
          </div>
          <div className="mt-3 flex justify-end">
            <Button data-testid={FINANCE.collectionCfgSubmit} onClick={saveCollection} disabled={busy}>
              {busy ? "Menyimpan\u2026" : "Simpan Penagihan"}
            </Button>
          </div>
        </section>
      ) : null}

      {/* Payment schemes */}
      <section className="rounded-xl border bg-card p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <h3 className="font-heading text-sm font-semibold">Skema Pembayaran (AR)</h3>
          <Button size="sm" variant="outline" data-testid={FINANCE.paymentSchemeAddBtn} onClick={() => setPayOpen(true)}>
            <Plus className="mr-1 h-3.5 w-3.5" /> Tambah
          </Button>
        </div>
        <div className="mt-3 space-y-2">
          {paySchemes.map((s) => (
            <div key={s.id} data-testid="payment-scheme-row" data-scheme-name={s.name}
              className="rounded-lg border bg-background p-3">
              <div className="flex items-center justify-between">
                <p className="flex items-center gap-1.5 font-medium">
                  {s.name}
                  {s.is_default ? <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-500" /> : null}
                </p>
                <span className="flex items-center gap-1">
                  <Button size="icon" variant="ghost" className="h-7 w-7"
                    data-testid="payment-scheme-edit-btn" data-scheme-name={s.name}
                    aria-label={`Ubah skema pembayaran ${s.name}`} title={`Ubah skema ${s.name}`}
                    onClick={() => setEditScheme({ kind: "payment-schemes", scheme: s })}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600"
                    data-testid="payment-scheme-delete-btn" data-scheme-name={s.name}
                    aria-label={`Hapus skema pembayaran ${s.name}`} title={`Hapus skema ${s.name}`}
                    onClick={() => setDelScheme_({ kind: "payment-schemes", scheme: s })}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </span>
              </div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {(s.items || []).map((it, i) => (
                  <span key={i} className="rounded-full border bg-card px-2 py-0.5 text-[11px] text-muted-foreground shadow-[var(--shadow-card)]">
                    {it.label} · {it.basis === "percent" ? `${it.value}%` : formatIDR(it.value)} · jatuh tempo +{it.due_offset_days} hari
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Commission schemes */}
      <section className="rounded-xl border bg-card p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <h3 className="font-heading text-sm font-semibold">Skema Komisi (bertingkat)</h3>
          <Button size="sm" variant="outline" data-testid={FINANCE.commissionSchemeAddBtn} onClick={() => setComOpen(true)}>
            <Plus className="mr-1 h-3.5 w-3.5" /> Tambah
          </Button>
        </div>
        <div className="mt-3 space-y-2">
          {comSchemes.map((s) => (
            <div key={s.id} data-testid="commission-scheme-row" data-scheme-name={s.name}
              className="rounded-lg border bg-background p-3">
              <div className="flex items-center justify-between">
                <p className="flex items-center gap-1.5 font-medium">
                  {s.name}
                  {s.is_default ? <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-500" /> : null}
                </p>
                <span className="flex items-center gap-1">
                  <Button size="icon" variant="ghost" className="h-7 w-7"
                    data-testid="commission-scheme-edit-btn" data-scheme-name={s.name}
                    aria-label={`Ubah skema komisi ${s.name}`} title={`Ubah skema ${s.name}`}
                    onClick={() => setEditScheme({ kind: "commission-schemes", scheme: s })}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button size="icon" variant="ghost" className="h-7 w-7 text-rose-600"
                    data-testid="commission-scheme-delete-btn" data-scheme-name={s.name}
                    aria-label={`Hapus skema komisi ${s.name}`} title={`Hapus skema ${s.name}`}
                    onClick={() => setDelScheme_({ kind: "commission-schemes", scheme: s })}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </span>
              </div>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                Basis: {labelOf("commission_basis", s.basis)} · Pemicu: {labelOf("commission_trigger", s.trigger)}
              </p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {(s.tiers || []).map((t, i) => (
                  <span key={i} className="rounded-full border bg-card px-2 py-0.5 text-[11px] text-muted-foreground shadow-[var(--shadow-card)]">
                    {formatIDR(t.min_amount)}–{t.max_amount ? formatIDR(t.max_amount) : "∞"} → {t.rate_pct}%
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <PaymentSchemeDialog open={payOpen} onOpenChange={setPayOpen} onDone={load} />
      <CommissionSchemeDialog open={comOpen} onOpenChange={setComOpen} onDone={load} />
      <RenameSchemeDialog kind={editScheme?.kind} scheme={editScheme?.scheme}
        open={!!editScheme} onOpenChange={(v) => !v && setEditScheme(null)} onDone={load} />
      <ConfirmDialog open={!!delScheme_} onOpenChange={(v) => !v && setDelScheme_(null)}
        title={`Hapus skema “${delScheme_?.scheme?.name || ""}”?`}
        description="Skema yang dihapus tidak lagi bisa dipilih pada deal baru. Deal yang sudah memakai skema ini tidak berubah."
        confirmLabel="Ya, hapus skema" busy={busy} onConfirm={delScheme}
        testId="scheme-delete-confirm" />
    </div>
  );
}
