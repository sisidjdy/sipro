import React, { useCallback, useEffect, useState } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import BeforeAfterCompare from "@/components/patterns/BeforeAfterCompare";
import PhotoGallery from "@/components/patterns/PhotoGallery";
import StatusPill from "@/components/patterns/StatusPill";
import RefLabel from "@/components/patterns/RefLabel";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR, formatDateWIB, formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { SITE_PLAN, FIELD } from "@/constants/testIds";

/** Umur listing / lama sampai laku — jujur menyebut mana yang mana. */
function domLabel(unit) {
  const dom = unit?.days_on_market;
  const days = typeof dom === "object" && dom ? dom.days : dom;
  const open = typeof dom === "object" && dom ? dom.open : unit?.dom_open !== false;
  if (days === null || days === undefined) return "—";
  return open ? `${days} hari dipasarkan (masih tersedia)` : `Laku setelah ${days} hari dipasarkan`;
}

function Row({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b py-2 last:border-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-right text-sm font-medium">{value}</span>
    </div>
  );
}

/**
 * Tingkat 3 progressive disclosure: drawer bertab yang merangkai data lintas modul
 * (spesifikasi, penjualan/AR/KPR, pembangunan per unit, riwayat) untuk satu kavling.
 */
export default function UnitDetailDrawer({ projectId, unit, onClose, canSeePrivate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!unit || !projectId) return;
    setLoading(true); setError("");
    try {
      const res = await api.get(`/site-plan/${projectId}/unit/${unit.id}`);
      setData(res.data?.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat detail kavling.");
    } finally { setLoading(false); }
  }, [projectId, unit]);

  useEffect(() => { load(); }, [load]);

  if (!unit) return null;
  const u = data?.unit || unit;
  const c = data?.construction;
  const ar = data?.ar;

  return (
    <Sheet open onOpenChange={(v) => { if (!v) onClose(); }}>
      <SheetContent data-testid={SITE_PLAN.detail} className="w-full overflow-y-auto sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle className="flex flex-wrap items-center gap-2">
            Kavling {u.code}
            <StatusPill status={u.status} group="unit_status" />
            {u.legal_stage ? <StatusPill status={u.legal_stage} group="legal_stage" /> : null}
          </SheetTitle>
          <SheetDescription>
            {u.type || "-"} · {formatIDR(u.price)}
            {u.corner ? " · kavling hook" : ""}
          </SheetDescription>
        </SheetHeader>

        {loading ? <LoadingCards count={2} /> : error ? <ErrorState message={error} onRetry={load} /> : (
          <Tabs defaultValue="summary" className="mt-4">
            <TabsList className="flex-wrap">
              <TabsTrigger data-testid={SITE_PLAN.tabSummary} value="summary">Ringkasan</TabsTrigger>
              <TabsTrigger data-testid={SITE_PLAN.tabSales} value="sales">Penjualan</TabsTrigger>
              <TabsTrigger data-testid={SITE_PLAN.tabBuild} value="build">Pembangunan</TabsTrigger>
              <TabsTrigger data-testid={SITE_PLAN.tabHistory} value="history">Riwayat</TabsTrigger>
            </TabsList>

            <TabsContent value="summary" className="mt-3">
              <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                <Row label="Tipe unit" value={u.type || "-"} />
                <Row label="Luas bangunan" value={`${u.luas_bangunan || 0} m²`} />
                <Row label="Luas tanah" value={`${u.luas_tanah || 0} m²`} />
                <Row label="Orientasi"
                  value={u.orientation ? <RefLabel group="unit_orientation" value={u.orientation} /> : "-"} />
                <Row label="Kavling hook" value={u.corner ? "Ya" : "Tidak"} />
                <Row label="Harga" value={formatIDR(u.price)} />
                <Row label="Harga per m² tanah"
                  value={u.luas_tanah ? formatIDR(Math.round(u.price / u.luas_tanah)) : "-"} />
                <Row label="Lama dipasarkan" value={domLabel(u)} />
                <Row label="Status pembayaran"
                  value={<RefLabel group="unit_payment_status" value={u.payment_status} />} />
              </div>
            </TabsContent>

            <TabsContent value="sales" className="mt-3 space-y-3">
              <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                <Row label="Pembeli" value={canSeePrivate ? (data?.lead?.name || u.buyer_name || "—") : "disembunyikan"} />
                <Row label="Tahap lead"
                  value={data?.lead?.stage ? <RefLabel group="lead_stage" value={data.lead.stage} /> : "—"} />
                <Row label="Sumber lead"
                  value={data?.lead?.source ? <RefLabel group="lead_source" value={data.lead.source} /> : "—"} />
                <Row label="Tahap legal"
                  value={data?.deal?.legal_stage ? <RefLabel group="legal_stage" value={data.deal.legal_stage} /> : "—"} />
                <Row label="Sales penanggung jawab" value={data?.deal?.assigned_to || "—"} />
              </div>
              {ar ? (
                <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                  <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
                    Tagihan (AR)
                  </p>
                  <Row label="Total kontrak" value={formatIDR(ar.total)} />
                  <Row label="Sudah dibayar" value={formatIDR(ar.paid)} />
                  <Row label="Sisa tagihan" value={formatIDR(ar.outstanding)} />
                  <div className="mt-2 space-y-1">
                    {(ar.schedule || []).map((s, i) => (
                      <div key={`${s.label}-${i}`}
                        className="flex items-center justify-between gap-2 rounded-md bg-secondary/40 px-2 py-1 text-xs">
                        <span>{s.label} · {formatDateWIB(s.due_date)}</span>
                        <span className="flex items-center gap-2">
                          <span className="tabular-nums">{formatIDR(s.amount)}</span>
                          <StatusPill status={s.status} group="ar_status" />
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="rounded-lg border bg-secondary/30 p-3 text-sm text-muted-foreground">
                  Belum ada jadwal tagihan untuk kavling ini.
                </p>
              )}
              {data?.financing ? (
                <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                  <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">KPR</p>
                  <Row label="Bank" value={data.financing.bank_name || "—"} />
                  <Row label="Status"
                    value={<RefLabel group="financing_status" value={data.financing.status} />} />
                  <Row label="Sudah dicairkan" value={formatIDR(data.financing.disbursed_total)} />
                </div>
              ) : null}
            </TabsContent>

            <TabsContent value="build" className="mt-3 space-y-3">
              <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-medium">Progres unit ini</span>
                  <span className="font-heading text-xl font-semibold tabular-nums">
                    {c?.progress || 0}%
                  </span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
                  <div className="h-full rounded-full bg-primary"
                    style={{ width: `${c?.progress || 0}%` }} />
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  Status: <RefLabel group="construction_status" value={c?.status} />
                </p>
              </div>
              <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
                  Fase konstruksi proyek
                </p>
                {(c?.phases || []).map((p) => (
                  <div key={p.name} className="mb-2">
                    <div className="flex items-center justify-between text-xs">
                      <span>{p.name} <span className="text-muted-foreground">(bobot {p.weight}%)</span></span>
                      <span className="tabular-nums">{p.progress}%</span>
                    </div>
                    <div className="mt-0.5 h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                      <div className="h-full rounded-full bg-emerald-500" style={{ width: `${p.progress}%` }} />
                    </div>
                  </div>
                ))}
              </div>
              <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
                  Foto progres terbaru ({(c?.photos || []).length})
                </p>
                <PhotoGallery photos={c?.photos || []} testId={SITE_PLAN.photoGrid}
                  itemTestId={SITE_PLAN.photoItem}
                  emptyText="Belum ada foto. Foto muncul otomatis dari Buku Harian lapangan dan temuan punch list berfoto pada kavling ini." />
              </div>
              <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
                  Bukti perbaikan: sebelum → sesudah ({(c?.repairs || []).length})
                </p>
                <div data-testid={FIELD.repairs}>
                  <BeforeAfterCompare repairs={c?.repairs || []}
                    emptyText="Belum ada bukti perbaikan. Lampirkan foto saat menutup temuan punch list pada kavling ini." />
                </div>
              </div>
              <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
                  Punch list unit ({(c?.punch_open || []).length} terbuka dari {c?.punch_total || 0})
                </p>
                {(c?.punch_open || []).length ? (c.punch_open.map((p, i) => (
                  <div key={`${p.title}-${i}`} className="flex items-center justify-between gap-2 py-1 text-xs">
                    <span>{p.title}</span>
                    <StatusPill status={p.severity} group="punch_severity" />
                  </div>
                ))) : (
                  <p className="text-xs text-muted-foreground">Tidak ada temuan terbuka.</p>
                )}
              </div>
            </TabsContent>

            <TabsContent value="history" className="mt-3">
              {(data?.activities || []).length ? (
                <div className="space-y-2">
                  {data.activities.map((a) => (
                    <div key={a.id} className="rounded-lg border bg-card p-2.5 shadow-[var(--shadow-card)]">
                      <p className="text-sm">{a.body}</p>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        {a.actor || "sistem"} · {formatDateTimeWIB(a.created_at)}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="rounded-lg border bg-secondary/30 p-3 text-sm text-muted-foreground">
                  Belum ada riwayat aktivitas untuk kavling ini.
                </p>
              )}
            </TabsContent>
          </Tabs>
        )}

        <div className="mt-4 flex justify-end">
          <Button variant="outline" onClick={onClose}>Tutup</Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
