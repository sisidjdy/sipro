import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Ban, Pencil } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import useTabParam from "@/hooks/useTabParam";
import EntityHeader from "@/components/patterns/EntityHeader";
import StatusPill from "@/components/patterns/StatusPill";
import DealPricingSheet, { DealPricingButton } from "@/components/sales/DealPricingSheet";
import EmptyState from "@/components/patterns/EmptyState";
import UnitBuildTab from "@/components/build/UnitBuildTab";
import UnitHandoverTab from "@/components/handover/UnitHandoverTab";
import PermitCoveragePanel from "@/components/permits/PermitCoveragePanel";
import CreateTaskDialog from "@/components/work/CreateTaskDialog";
import DeleteEntityButton from "@/components/patterns/DeleteEntityButton";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { formatDateTimeWIB, formatIDR } from "@/utils/formatters";
import { MASTERPLAN, P50 } from "@/constants/testIds";

function Row({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b py-2 last:border-0">
      <span className="text-xs uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="text-right text-sm font-medium">{value ?? "-"}</span>
    </div>
  );
}

/** UNIT 360 (Fase 39): satu halaman berisi penjualan + pembangunan + dokumen + riwayat. */
export default function UnitDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useTabParam("summary");
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  const canManage = can("units", "update");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [edit, setEdit] = useState(null);
  const [blockForm, setBlockForm] = useState(null);
  const [pricingFor, setPricingFor] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get(`/masterplan/units/${id}/360`);
      setData(res.data.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat unit.");
    } finally { setLoading(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const saveEdit = async () => {
    try {
      await api.patch(`/masterplan/units/${id}`, {
        price: edit.price ? Number(edit.price) : undefined,
        excess_land_m2: edit.excess_land_m2 !== "" ? Number(edit.excess_land_m2) : undefined,
        excess_land_price_agreed: edit.excess_land_price_agreed !== ""
          ? Number(edit.excess_land_price_agreed) : undefined,
        reason: edit.reason || undefined,
      });
      toast.success("Unit diperbarui.");
      setEdit(null); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memperbarui unit."); }
  };

  const saveBlock = async () => {
    try {
      await api.post(`/masterplan/units/${id}/block`, {
        blocked: blockForm.blocked, reason: blockForm.reason,
      });
      toast.success(blockForm.blocked ? "Unit diblokir." : "Blokir unit dibuka.");
      setBlockForm(null); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengubah blokir unit."); }
  };

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const u = data?.unit || {};
  const blocked = u.status === "blocked";

  return (
    <div data-testid={MASTERPLAN.unitPage} className="space-y-5">
      <EntityHeader
        kicker={`${data?.project?.name || "Proyek"} · ${data?.cluster?.code || "-"} / ${data?.block?.code || "-"}`}
        title={`Unit ${u.code}`}
        subtitle={`${u.type || "-"} · LT ${u.luas_tanah ?? "-"} m² / LB ${u.luas_bangunan ?? "-"} m²`}
        backLabel="Kembali"
        chips={[
          { label: "Harga", value: formatIDR(u.price) },
          { label: "Status jual", value: u.status_label },
          { label: "Status bangun", value: u.construction_label },
          u.corner ? { label: "Posisi", value: "Hook / sudut" } : null,
          u.excess_land_m2 ? { label: "Kelebihan tanah", value: `${u.excess_land_m2} m²` } : null,
        ]}
        actions={(
          <>
            {can("work_tasks", "create") ? (
              <CreateTaskDialog triggerLabel="Buat tugas" triggerVariant="outline"
                preset={{ type: "unit", id,
                  label: `${u.code || id}${data?.block?.code ? ` — Blok ${data.block.code}` : ""}` }} />
            ) : null}
            {canManage ? (
              <>
                <Button data-testid={MASTERPLAN.unitEditOpen} size="sm" variant="secondary"
                  onClick={() => setEdit({ price: u.price || "",
                    excess_land_m2: u.excess_land_m2 ?? "",
                    excess_land_price_agreed: u.excess_land_price_agreed ?? "", reason: "" })}>
                  <Pencil className="mr-1.5 h-4 w-4" /> Ubah unit
                </Button>
                <Button data-testid={MASTERPLAN.unitBlockOpen} size="sm" variant="outline"
                  onClick={() => setBlockForm({ blocked: !blocked, reason: "" })}>
                  <Ban className="mr-1.5 h-4 w-4" /> {blocked ? "Buka blokir" : "Blokir unit"}
                </Button>
              </>
            ) : null}
            {can("units", "delete") && u.project_id ? (
              <DeleteEntityButton entity="Unit" name={u.code} testId="unit-delete"
                checkUrl={`/projects/${u.project_id}/units/${id}/delete-check`}
                deleteUrl={`/projects/${u.project_id}/units/${id}`}
                onDeleted={() => navigate(`/projects/${u.project_id}`)} />
            ) : null}
          </>
        )} />

      <Tabs value={tab} onValueChange={setTab} className="space-y-4">
        <TabsList className="flex-wrap">
          <TabsTrigger data-testid={MASTERPLAN.unitTabSummary} value="summary">Ringkasan</TabsTrigger>
          <TabsTrigger data-testid={MASTERPLAN.unitTabSales} value="sales">Penjualan</TabsTrigger>
          <TabsTrigger data-testid={MASTERPLAN.unitTabBuild} value="build">Pembangunan</TabsTrigger>
          <TabsTrigger data-testid={MASTERPLAN.unitTabDocs} value="docs">Dokumen & Izin</TabsTrigger>
          {/* Fase 50A: serah terima & garansi menempel pada RUMAH, jadi pintunya di sini —
              bukan menu sidebar baru. */}
          <TabsTrigger data-testid={P50.unitTabHandover} value="handover">
            Serah Terima & Garansi
          </TabsTrigger>
          <TabsTrigger data-testid={MASTERPLAN.unitTabHistory} value="history">Riwayat</TabsTrigger>
        </TabsList>

        <TabsContent value="summary" className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
            <h2 className="mb-2 font-heading text-base font-semibold">Spesifikasi</h2>
            <Row label="Tipe" value={u.type} />
            <Row label="Luas tanah" value={u.luas_tanah ? `${u.luas_tanah} m²` : null} />
            <Row label="Luas bangunan" value={u.luas_bangunan ? `${u.luas_bangunan} m²` : null} />
            <Row label="Posisi" value={u.corner ? "Hook / sudut" : "Tengah"} />
            <Row label="Kelebihan tanah"
              value={u.excess_land_m2 ? `${u.excess_land_m2} m²` : "tidak ada"} />
            <Row label="Harga kelebihan tanah disepakati"
              value={u.excess_land_price_agreed
                ? `${formatIDR(u.excess_land_price_agreed)} /m²` : "belum disepakati"} />
            <Row label="Harga unit" value={formatIDR(u.price)} />
          </div>
          <div className="rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
            <h2 className="mb-2 font-heading text-base font-semibold">Usulan spek tambahan</h2>
            {(data?.suggested_addons || []).length ? (
              <div className="space-y-2">
                {data.suggested_addons.map((a) => (
                  <div key={a.code} className="rounded-md border bg-secondary p-2 text-sm">
                    <div className="font-medium">{a.name}</div>
                    <div className="text-xs text-muted-foreground">{a.reason}</div>
                    <div className="text-xs">
                      {formatIDR(a.unit_price)}{a.pricing_mode === "per_m2" ? " /m²" : ""}
                      {a.suggested_qty > 1 ? ` × ${a.suggested_qty}` : ""}
                      {a.requires_document ? ` · wajib dokumen ${a.requires_document}` : ""}
                    </div>
                  </div>
                ))}
                <p className="text-xs text-muted-foreground">
                  Add-on dipilih resmi saat reservasi/booking dan menjadi komponen
                  terpisah di kontrak & keuangan.
                </p>
              </div>
            ) : (
              <EmptyState title="Tidak ada usulan"
                description="Usulan muncul bila unit hook atau punya kelebihan tanah." />
            )}
          </div>
        </TabsContent>

        <TabsContent value="sales" className="space-y-4">
          <div className="rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
            <h2 className="mb-2 font-heading text-base font-semibold">Pembeli & transaksi</h2>
            <Row label="Status penjualan"
              value={<StatusPill status={u.status} group="unit_status" />} />
            <Row label="Pembeli" value={data?.customer?.name || u.lead_name || "belum ada"} />
            <Row label="Transaksi (deal)" value={`${(data?.deals || []).length} transaksi`} />
            <Row label="Tagihan terbit" value={`${(data?.invoices || []).length} tagihan`} />
            <Row label="Status pembayaran" value={u.payment_status || "belum ada"} />
          </div>
          {(data?.deals || []).length ? (
            <div className="overflow-x-auto rounded-md border bg-card shadow-[var(--shadow-card)]">
              <table className="w-full text-sm">
                <thead className="bg-secondary text-left">
                  <tr>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Harga</th>
                    <th className="px-3 py-2 font-medium">Potongan</th>
                    <th className="px-3 py-2 font-medium">Booking fee</th>
                    <th className="px-3 py-2 font-medium">Dibuat</th>
                    <th className="px-3 py-2 font-medium text-right">Rincian</th>
                  </tr>
                </thead>
                <tbody>
                  {data.deals.map((d) => (
                    <tr key={d.id} className="border-t">
                      <td className="px-3 py-2">
                        <StatusPill status={d.status} group="deal_status" />
                      </td>
                      <td className="px-3 py-2 tabular-nums">{formatIDR(d.price)}</td>
                      <td className="px-3 py-2 tabular-nums text-rose-700">
                        {d.discount ? `-${formatIDR(d.discount)}` : <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="px-3 py-2 tabular-nums">{formatIDR(d.booking_fee)}</td>
                      <td className="px-3 py-2 text-xs text-muted-foreground">
                        {formatDateTimeWIB(d.created_at)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <DealPricingButton deal={d} onOpen={(x) => setPricingFor(x.id)} variant="ghost" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          <DealPricingSheet dealId={pricingFor} open={!!pricingFor}
            onOpenChange={(v) => !v && setPricingFor(null)} />
        </TabsContent>

        <TabsContent value="build">
          {/* Fase 46 (dok 29 §3): tab ini dulu hanya 4 baris read-only sehingga semua aksi
              konstruksi harus dicari di layar monitoring lintas unit. Sekarang seluruh
              pekerjaan satu rumah ada di sini: kesiapan mulai bangun, kurva-S, langkah +
              bukti, mutu, dan temuan. */}
          <UnitBuildTab unitId={id} projectId={u.project_id || data?.project?.id}
            unitCode={u.code} onChanged={load} />
        </TabsContent>

        <TabsContent value="docs" className="space-y-3">
          {/* Fase 46 (dok 29 §5): izin menempel pada objek — panel ini menampilkan izin unit
              BESERTA warisan dari blok/cluster/proyek, kesehatan masa berlakunya, dan aksi
              tambah/perpanjang. Sebelumnya hanya daftar mati tanpa masa berlaku. */}
          <PermitCoveragePanel unitId={id}
            title={`Perizinan yang berlaku untuk unit ${u.code || ""}`} />
          <div className="rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
            <h2 className="mb-2 font-heading text-base font-semibold">Dokumen unit</h2>
            {(data?.documents || []).length ? (
              <ul className="space-y-1 text-sm">
                {data.documents.map((d) => (
                  <li key={d.id} className="flex items-center justify-between border-b py-1">
                    <span>{d.requirement_label}</span>
                    <StatusPill status={d.status} group="doc_submission_status" />
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="Belum ada dokumen"
                description="Dokumen syarat diunggah dari profil lead/customer terkait." />
            )}
          </div>
        </TabsContent>

        <TabsContent value="handover" className="space-y-4">
          <UnitHandoverTab unitId={id} unitCode={u.code} />
        </TabsContent>

        <TabsContent value="history">
          <div className="rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
            <h2 className="mb-3 font-heading text-base font-semibold">Riwayat status & harga</h2>
            {(data?.history || []).length ? (
              <ol className="space-y-2">
                {data.history.map((h, i) => (
                  <li key={i} className="rounded-md border bg-secondary p-2 text-sm">
                    <div className="font-medium">
                      {h.field === "price" ? "Harga" : "Status"}: {String(h.from ?? "-")} → {String(h.to)}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {h.actor} · {formatDateTimeWIB(h.at)}
                      {h.estimated ? " · (hasil migrasi, perkiraan)" : ""}
                    </div>
                    {h.reason ? <div className="text-xs">Alasan: {h.reason}</div> : null}
                  </li>
                ))}
              </ol>
            ) : <EmptyState title="Belum ada riwayat" />}
          </div>
        </TabsContent>
      </Tabs>

      <Dialog open={!!edit} onOpenChange={(o) => { if (!o) setEdit(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ubah unit {u.code}</DialogTitle>
            <DialogDescription>
              Perubahan harga pada unit yang sudah terikat transaksi wajib beralasan dan tercatat.
            </DialogDescription>
          </DialogHeader>
          {edit ? (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="un-price">Harga unit (Rp)</Label>
                <RupiahInput id="un-price" data-testid={MASTERPLAN.unitEditPrice}
                  value={edit.price}
                  onChange={(e) => setEdit({ ...edit, price: e.target.value })} />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="un-excess">Kelebihan tanah (m²)</Label>
                  <Input id="un-excess" data-testid={MASTERPLAN.unitEditExcess} type="number"
                    value={edit.excess_land_m2}
                    onChange={(e) => setEdit({ ...edit, excess_land_m2: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="un-excess-price">Harga disepakati (Rp/m²)</Label>
                  <RupiahInput id="un-excess-price" data-testid={MASTERPLAN.unitEditExcessPrice} value={edit.excess_land_price_agreed}
                    onChange={(e) => setEdit({ ...edit,
                      excess_land_price_agreed: e.target.value })} />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="un-reason">Alasan perubahan</Label>
                <Textarea id="un-reason" data-testid={MASTERPLAN.unitEditReason} rows={2}
                  placeholder="Contoh: hasil nego dengan pembeli, disetujui manajer"
                  value={edit.reason}
                  onChange={(e) => setEdit({ ...edit, reason: e.target.value })} />
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEdit(null)}>Batal</Button>
            <Button data-testid={MASTERPLAN.unitEditSubmit} onClick={saveEdit}>Simpan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!blockForm} onOpenChange={(o) => { if (!o) setBlockForm(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{blockForm?.blocked ? "Blokir unit" : "Buka blokir unit"}</DialogTitle>
            <DialogDescription>
              Unit yang diblokir tidak muncul sebagai tersedia (mis. rumah contoh, sengketa).
            </DialogDescription>
          </DialogHeader>
          {blockForm ? (
            <div className="space-y-1.5">
              <Label htmlFor="bl-reason">Alasan (wajib)</Label>
              <Textarea id="bl-reason" data-testid={MASTERPLAN.unitBlockReason} rows={2}
                value={blockForm.reason}
                onChange={(e) => setBlockForm({ ...blockForm, reason: e.target.value })} />
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setBlockForm(null)}>Batal</Button>
            <Button data-testid={MASTERPLAN.unitBlockSubmit} onClick={saveBlock}
              disabled={!blockForm?.reason?.trim()}>Simpan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
