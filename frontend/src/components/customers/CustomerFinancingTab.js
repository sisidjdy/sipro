import React, { useState } from "react";
import { Banknote, CreditCard, Plus, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import EmptyState from "@/components/patterns/EmptyState";
import {
  AddFinancingDialog, SlikDialog, DisburseDialog,
} from "@/components/customers/FinancingDialogs";
import { formatDateWIB } from "@/utils/formatters";
import { CUSTOMERS } from "@/constants/testIds";

/**
 * CustomerFinancingTab — pengajuan KPR: plafon, DP, tenor, SLIK, pencairan.
 *
 * Yang ADA di sini: pengajuan KPR beserta hasil SLIK dan pencairannya — data pembiayaan yang
 * memang sudah dikelola sistem. Yang BELUM dibangun: alur bertahap berkas → bank → appraisal
 * → SP3K → akad → pencairan lengkap dengan gerbang bukti per tahap dan usulan refund 50%
 * bila bank menolak. Sengaja TIDAK disebut dengan nomor fase: urutan pengerjaan pernah
 * berubah dan janji bernomor jadi menyesatkan.
 */
export default function CustomerFinancingTab({ customer, financings = [], onChanged }) {
  const [addOpen, setAddOpen] = useState(false);
  const [slikFor, setSlikFor] = useState(null);
  const [disburseFor, setDisburseFor] = useState(null);

  return (
    <div data-testid={CUSTOMERS.financingSection} className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <CreditCard className="h-4 w-4" /> Pengajuan pembiayaan (KPR) pelanggan ini.
        </p>
        <Button data-testid={CUSTOMERS.financingAddBtn} size="sm" variant="outline"
          onClick={() => setAddOpen(true)}>
          <Plus className="mr-1.5 h-4 w-4" /> Ajukan KPR
        </Button>
      </div>

      {financings.length === 0 ? (
        <EmptyState icon={CreditCard} title="Belum ada pengajuan KPR"
          description="Ajukan KPR untuk pelanggan ini bila skema pembayarannya memakai bank."
          actionLabel="Ajukan KPR" onAction={() => setAddOpen(true)} />
      ) : (
        <div className="space-y-3">
          {financings.map((f) => {
            const remaining = (f.plafon || 0) - (f.disbursed_total || 0);
            return (
              <div key={f.id} data-testid={CUSTOMERS.financingRow}
                className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{f.bank_name}</span>
                  <StatusPill status={f.status} group="financing_status" />
                </div>
                <div className="mt-1.5 grid gap-x-4 gap-y-1 text-xs text-muted-foreground sm:grid-cols-3">
                  <span>Plafon: <MoneyText value={f.plafon} className="font-medium text-foreground" /></span>
                  <span>DP: <MoneyText value={f.dp_amount} className="font-medium text-foreground" /></span>
                  <span>Tenor: <b className="text-foreground">{f.tenor_months} bln</b></span>
                  <span>SLIK: <b className="text-foreground">{f.slik_status}</b></span>
                  <span>Dicairkan: <MoneyText value={f.disbursed_total} className="font-medium text-foreground" /></span>
                  <span>Sisa: <MoneyText value={remaining} className="font-medium text-foreground" /></span>
                </div>
                {f.slik_prescreen ? (
                  <p data-testid="financing-prescreen-note" data-financing={f.id}
                    className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-900">
                    Pra-skrining lead: <b>{f.slik_prescreen.label || f.slik_prescreen.status}</b>
                    {" "}(SIMULASI · {(f.slik_prescreen.evidence || []).length} bukti) —
                    hasil resmi bank {f.slik_status === "pending" ? "belum masuk" : f.slik_status}.
                  </p>
                ) : null}
                {(f.disbursements || []).length > 0 ? (
                  <div className="mt-2 border-t pt-2 text-xs">
                    {f.disbursements.map((d) => (
                      <div key={d.id} className="flex justify-between py-0.5">
                        <span className="text-muted-foreground">
                          {d.milestone} · {formatDateWIB(d.created_at)}
                        </span>
                        <MoneyText value={d.amount} />
                      </div>
                    ))}
                  </div>
                ) : null}
                <div className="mt-2 flex gap-2">
                  <Button data-testid={CUSTOMERS.slikBtn} size="sm" variant="outline"
                    onClick={() => setSlikFor(f)}>
                    <ShieldCheck className="mr-1.5 h-3.5 w-3.5" /> SLIK
                  </Button>
                  <Button data-testid={CUSTOMERS.disburseBtn} size="sm" variant="outline"
                    disabled={!(["approved", "disbursing"].includes(f.status))}
                    onClick={() => setDisburseFor(f)}>
                    <Banknote className="mr-1.5 h-3.5 w-3.5" /> Cairkan
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <AddFinancingDialog open={addOpen} onOpenChange={setAddOpen} customer={customer}
        onDone={onChanged} />
      <SlikDialog open={!!slikFor} onOpenChange={(v) => !v && setSlikFor(null)}
        financing={slikFor} onDone={onChanged} />
      <DisburseDialog open={!!disburseFor} onOpenChange={(v) => !v && setDisburseFor(null)}
        financing={disburseFor} onDone={onChanged} />
    </div>
  );
}
