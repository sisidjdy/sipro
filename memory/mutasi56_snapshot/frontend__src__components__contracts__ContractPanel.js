import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PlayCircle, Receipt, ScrollText, ShieldOff, Wallet } from "lucide-react";

import { Button } from "@/components/ui/button";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import EmptyState from "@/components/patterns/EmptyState";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import CostsDialog from "@/components/contracts/CostsDialog";
import LegalTimeline from "@/components/contracts/LegalTimeline";
import KprPanel from "@/components/contracts/KprPanel";
import ContractDocuments from "@/components/contracts/ContractDocuments";
import CancellationPanel from "@/components/contracts/CancellationPanel";
// Fase 57A — skema pembayaran yang dipakai kontrak ini (dan asalnya) harus TERLIHAT.
import ContractSchemePicker from "@/components/contracts/ContractSchemePicker";
import { useAuth } from "@/context/AuthContext";
import { formatDateWIB, formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { P53 } from "@/constants/testIds";

/**
 * ContractPanel — KONTRAK PEMBELI: rincian komponen, rencana bayar, tahap legal, KPR,
 * dan dokumen yang bisa dicetak.
 *
 * Dipakai dua tempat: tab “Kontrak & Legal” pada profil pembeli, dan kartu ringkas pada tab
 * “Unit & SPR” profil lead (lewat `dealId`). Satu komponen supaya kedua layar tidak pernah
 * bercerita berbeda tentang kontrak yang sama.
 *
 * Kejujuran angka yang dipaksakan panel ini:
 *   • komponen biaya yang BELUM diisi ditulis “belum diisi” (bukan Rp 0) dan totalnya
 *     ditandai SEMENTARA;
 *   • rencana bayar dibaca dari tagihan NYATA (AR) — bila belum ada, sebabnya ditulis;
 *   • jatuh tempo yang bergantung peristiwa (pembangunan 100%, akad) ditandai supaya tidak
 *     dibaca sebagai tanggal pasti.
 */
export default function ContractPanel({ dealId = null, contractId = null, customerId = null,
  compact = false, onChanged = null }) {
  const { can } = useAuth();
  const mayUpdate = can("contracts", "update");
  const [state, setState] = useState({ loading: true, error: "", reason: "", reasonCode: "" });
  const [contract, setContract] = useState(null);
  const [costsOpen, setCostsOpen] = useState(false);

  const load = useCallback(async () => {
    setState({ loading: true, error: "", reason: "", reasonCode: "" });
    try {
      let res;
      if (contractId) res = await api.get(`/contracts/${contractId}`);
      else if (dealId) res = await api.get(`/contracts/by-deal/${dealId}`);
      else {
        const list = await api.get("/contracts", { params: { customer_id: customerId } });
        const first = (list.data.data || [])[0];
        if (!first) {
          setContract(null);
          setState({ loading: false, error: "", reason: list.data.reason || "",
            reasonCode: list.data.reason_code || "" });
          return;
        }
        res = await api.get(`/contracts/${first.id}`);
      }
      setContract(res.data.data);
      setState({ loading: false, error: "", reason: res.data.reason || "", reasonCode: "" });
    } catch (e) {
      setState({ loading: false, reason: "", reasonCode: "",
        error: e?.response?.data?.detail || "Gagal memuat kontrak." });
    }
  }, [contractId, dealId, customerId]);

  useEffect(() => { load(); }, [load]);

  const refresh = () => { load(); onChanged && onChanged(); };

  const activate = async () => {
    try {
      await api.post(`/contracts/${contract.id}/activate`);
      refresh();
    } catch (e) {
      setState((s) => ({ ...s,
        error: e?.response?.data?.detail || "Gagal mengaktifkan kontrak." }));
    }
  };

  if (state.loading) return <LoadingCards count={compact ? 1 : 3} />;
  if (state.error) return <ErrorState message={state.error} onRetry={load} />;
  if (!contract) {
    // Dua keadaan yang TIDAK BOLEH bercerita sama:
    //   • memang belum ada kontrak (lead belum jadi pembeli), dan
    //   • kontraknya ADA tetapi di luar lingkup data peran ini.
    // Menulis "Belum ada kontrak" untuk keadaan kedua adalah layar yang berbohong —
    // pelajaran yang sama dengan `/materials` pada Fase 48 dan `PanelStateView` Fase 52.
    if (state.reasonCode === "di_luar_lingkup") {
      return (
        <EmptyState testId={P53.contractScoped} icon={ShieldOff}
          title="Kontrak ini di luar lingkup data Anda"
          description={state.reason} />
      );
    }
    return (
      <EmptyState testId={P53.contractEmpty} icon={ScrollText} title="Belum ada kontrak"
        description={state.reason
          || "Kontrak lahir saat lead dijadikan PEMBELI (setelah booking dikonfirmasi)."} />
    );
  }

  const bd = contract.breakdown || {};
  const plan = contract.payment_plan || {};
  const inv = plan.invoice || {};

  const header = (
    <div className="flex flex-wrap items-start justify-between gap-3 rounded-lg border bg-card p-4">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
          <ScrollText className="h-4 w-4" />
          <span data-testid={P53.contractNumber} className="font-mono">{contract.number}</span>
          <StatusPill status={contract.state} group="contract_state" />
          <StatusPill status={contract.legal_stage} group="contract_legal_stage" />
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {contract.customer_name} · unit{" "}
          <Link className="text-primary hover:underline" to={`/units/${contract.unit_id}`}>
            {contract.unit_code}
          </Link>{" "}· skema <strong>{contract.scheme_label}</strong>
          {contract.activated_at ? ` · aktif sejak ${formatDateWIB(contract.activated_at)}` : ""}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {mayUpdate ? (
          <Button data-testid={P53.costsBtn} size="sm" variant="outline"
            onClick={() => setCostsOpen(true)}>
            <Wallet className="mr-1.5 h-3.5 w-3.5" /> Komponen biaya
          </Button>
        ) : null}
        {mayUpdate && contract.state === "draft" ? (
          <Button data-testid={P53.activateBtn} size="sm" onClick={activate}>
            <PlayCircle className="mr-1.5 h-3.5 w-3.5" /> Aktifkan kontrak
          </Button>
        ) : null}
      </div>
    </div>
  );

  if (compact) {
    return (
      <div className="space-y-3">
        {header}
        <div className="rounded-lg border bg-card p-4 text-sm">
          <p className="flex flex-wrap items-baseline gap-2">
            <span className="text-muted-foreground">Total ditagihkan:</span>
            <MoneyText value={bd.total_bill} className="font-medium" />
            {bd.total_is_provisional ? (
              <span data-testid={P53.totalProvisional}
                className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-900">
                masih sementara
              </span>
            ) : null}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">{bd.note || ""}</p>
          {/* Penanda tab HARUS `?tab=` — `CustomerProfilePage` membaca `paramKey="tab"`.
              Menulis `?hub=` membuat tautan mendarat di tab pertama (Ringkasan) sambil
              berpura-pura membawa pemakai ke Kontrak & Legal. */}
          <Link to={`/customers/${contract.customer_id}?tab=kontrak53`}
            className="mt-2 inline-block text-xs font-medium text-primary hover:underline">
            Buka Kontrak & Legal →
          </Link>
        </div>
        {costsOpen ? (
          <CostsDialog contract={contract} open={costsOpen} onOpenChange={setCostsOpen}
            onSaved={refresh} />
        ) : null}
      </div>
    );
  }

  return (
    <div data-testid={P53.contractPanel} className="space-y-4">
      {header}

      {/* ---------------- rincian komponen (satu baris per komponen) ---------------- */}
      <section className="space-y-2 rounded-lg border bg-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="font-heading text-base font-semibold">Rincian harga & biaya</h3>
            <p className="text-xs text-muted-foreground">
              Setiap komponen adalah BARIS tersendiri — add-on, kelebihan tanah, hook, dan
              biaya transaksi tidak dilebur ke harga unit.
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-muted-foreground">Total ditagihkan</p>
            <MoneyText value={bd.total_bill} className="text-lg font-semibold" />
            {bd.total_is_provisional ? (
              <p data-testid={P53.totalProvisional} className="text-[11px] text-amber-700">
                {/* LABEL manusia, bukan kode kolom. `costs_incomplete` (BPHTB, NOTARY_FEE,
                    PPH_SELLER, …) adalah nama field — pemakai tidak berutang pengetahuan itu
                    kepada kita. */}
                masih SEMENTARA — {(bd.costs_incomplete_labels
                  || bd.costs_incomplete || []).join(", ")} belum diisi
              </p>
            ) : null}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                <th className="py-2">Komponen</th>
                <th className="py-2">Perlakuan keuangan</th>
                <th className="py-2 text-right">Nilai</th>
              </tr>
            </thead>
            <tbody>
              {(bd.rows || []).map((r) => (
                <tr key={r.code} data-testid={P53.breakdownRow} data-code={r.code}
                  data-state={r.state} className="border-b last:border-0">
                  <td className="py-2">
                    <p className="font-medium">{r.label}</p>
                    {r.note ? (
                      <p className="text-[11px] text-muted-foreground">{r.note}</p>
                    ) : null}
                    {(r.meta?.items || []).map((it) => (
                      <p key={it.code} className="text-[11px] text-muted-foreground">
                        • {it.name} {it.qty ? `· ${it.qty} ${it.uom || ""}` : ""} —{" "}
                        {formatIDR(it.amount)}
                      </p>
                    ))}
                  </td>
                  <td className="py-2 text-xs text-muted-foreground">{r.finance_treatment}</td>
                  <td className="py-2 text-right">
                    {r.amount === null ? (
                      <span data-testid={P53.breakdownEmptyState}
                        className="text-xs italic text-muted-foreground">{r.state_label}</span>
                    ) : <MoneyText value={r.amount} />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {contract.scheme === "kpr" && bd.self_funding !== null
          && bd.self_funding !== undefined ? (
            <p className="text-xs text-muted-foreground">
              Selisih pendanaan (harga nett − plafon) ={" "}
              <strong>{formatIDR(bd.self_funding)}</strong> — menjadi kewajiban pembeli
              sebelum akad kredit.
            </p>
          ) : null}
      </section>

      {/* ---------------- rencana bayar dari AR ---------------- */}
      <section className="space-y-2 rounded-lg border bg-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="flex items-center gap-2 font-heading text-base font-semibold">
              <Receipt className="h-4 w-4" /> Rencana bayar
            </h3>
            <p className="text-xs text-muted-foreground">
              Dibaca dari tagihan NYATA (AR) — bukan tabel kedua yang bisa berbeda.
            </p>
          </div>
          {plan.state === "ada" ? (
            <div className="text-right text-xs">
              <p>Total <strong>{formatIDR(inv.total)}</strong></p>
              <p>Terbayar {formatIDR(inv.paid)} · sisa {formatIDR(inv.outstanding)}</p>
            </div>
          ) : null}
        </div>
        <ContractSchemePicker contract={contract} onChanged={refresh} />
        {plan.state === "ada" ? (
          <div className="space-y-1.5">
            {(plan.terms || []).map((t) => (
              <div key={t.id || t.no} data-testid={P53.planRow}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-background p-2.5 text-sm">
                <div className="min-w-0">
                  <p className="font-medium">{t.no}. {t.label}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {t.due_date ? `Jatuh tempo ${formatDateWIB(t.due_date)}` : ""}
                    {t.due_rule ? ` · ${t.due_rule}` : ""}
                    {t.event_based ? " (tanggal mengikuti peristiwa, bukan tanggal pasti)" : ""}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <MoneyText value={t.amount} className="text-sm" />
                  <StatusPill status={t.status} group="ar_status" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p data-testid={P53.planEmpty}
            className="rounded-lg border border-dashed bg-secondary/40 p-4 text-sm text-muted-foreground">
            {plan.reason || "Rencana bayar belum ada."}
            {(plan.rules || []).length ? (
              <span className="mt-2 block">
                Aturan skema ini: {(plan.rules || []).map((r) => r.label).join(" → ")}.
              </span>
            ) : null}
          </p>
        )}
      </section>

      <LegalTimeline contract={contract} onChanged={refresh} />
      <KprPanel contract={contract} onChanged={refresh} />
      <ContractDocuments contract={contract} onChanged={refresh} />
      <CancellationPanel contract={contract} onChanged={refresh} />

      {costsOpen ? (
        <CostsDialog contract={contract} open={costsOpen} onOpenChange={setCostsOpen}
          onSaved={refresh} />
      ) : null}
    </div>
  );
}
