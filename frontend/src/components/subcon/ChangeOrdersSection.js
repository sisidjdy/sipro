import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, GitBranch, CheckCircle2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import StatusPill from "@/components/patterns/StatusPill";
import { formatIDR } from "@/utils/formatters";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { CHANGE_ORDERS } from "@/constants/testIds";


export default function ChangeOrdersSection({ spk, onChanged }) {
  const { can } = useAuth();
  // Izin dari izin EFEKTIF (`GET /auth/me`), bukan daftar peran yang ditulis ulang di
  // layar: matriks RBAC bisa diubah admin lewat Pusat Konfigurasi, jadi daftar hardcode
  // membuat tombol berbeda dengan jawaban server (tombol mati 403, atau tombol hilang
  // padahal peran itu berhak).
  const canCreate = can("change_orders", "create");
  const canApprove = can("change_orders", "approve");

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({ title: "", value_delta: "", time_extension_days: "", reason: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!spk?.id) return;
    setLoading(true);
    try {
      const r = await api.get("/subcon/change-orders", { params: { spk_id: spk.id } });
      setRows(r.data.data || []);
    } catch { /* noop */ } finally { setLoading(false); }
  }, [spk?.id]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn, okMsg) => {
    setBusy(true);
    try { await fn(); toast.success(okMsg); load(); onChanged && onChanged(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Aksi gagal."); }
    finally { setBusy(false); }
  };

  const create = () => {
    if (!form.title.trim()) { toast.error("Judul wajib diisi."); return; }
    return act(() => api.post("/subcon/change-orders", {
      spk_id: spk.id, title: form.title, value_delta: Number(form.value_delta) || 0,
      time_extension_days: Number(form.time_extension_days) || 0, reason: form.reason || undefined,
    }), "Change Order dibuat.").then(() => {
      setAddOpen(false); setForm({ title: "", value_delta: "", time_extension_days: "", reason: "" });
    });
  };

  return (
    <div data-testid={CHANGE_ORDERS.section} className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-sm font-semibold"><GitBranch className="h-4 w-4 text-primary" /> Change Order (Addendum)</p>
        {canCreate ? (
          <Button size="sm" variant="outline" data-testid={CHANGE_ORDERS.addBtn} onClick={() => setAddOpen(true)}>
            <Plus className="mr-1 h-3.5 w-3.5" /> Buat CO
          </Button>
        ) : null}
      </div>

      {loading ? <p className="text-sm text-muted-foreground">Memuat…</p> :
        !rows.length ? <p className="text-sm text-muted-foreground">Belum ada change order.</p> : (
          <div className="space-y-2">
            {rows.map((co) => (
              <div key={co.id} data-testid={CHANGE_ORDERS.row} className="rounded-lg border bg-background p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{co.co_number}</span>
                  <StatusPill status={co.status} group="change_order_status" />
                </div>
                <p className="mt-1 text-sm">{co.title}</p>
                <p className="text-sm tabular-nums">
                  Nilai: <span className={co.value_delta >= 0 ? "text-emerald-700" : "text-rose-700"}>
                    {co.value_delta >= 0 ? "+" : ""}{formatIDR(co.value_delta)}
                  </span>
                  {co.time_extension_days ? <span className="text-muted-foreground"> · +{co.time_extension_days} hari</span> : null}
                  {co.status === "approved" ? <span className="text-muted-foreground"> · {formatIDR(co.original_value)} → {formatIDR(co.new_value)}</span> : null}
                </p>
                {co.status === "draft" && canApprove ? (
                  <div className="mt-2 flex gap-2">
                    <Button size="sm" data-testid={CHANGE_ORDERS.approveBtn} disabled={busy}
                      onClick={() => act(() => api.post(`/subcon/change-orders/${co.id}/approve`), "Change Order disetujui.")}>
                      <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> Setujui
                    </Button>
                    <Button size="sm" variant="ghost" data-testid={CHANGE_ORDERS.rejectBtn} disabled={busy}
                      onClick={() => act(() => api.post(`/subcon/change-orders/${co.id}/reject`, { note: "Ditolak" }), "Change Order ditolak.")}>
                      <XCircle className="mr-1 h-3.5 w-3.5 text-rose-600" /> Tolak
                    </Button>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )}

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Buat Change Order</DialogTitle>
            <DialogDescription>Perubahan nilai/waktu kontrak SPK {spk?.spk_number}. Nilai kontrak diperbarui saat disetujui.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5"><Label htmlFor="changeorderssection-judul">Judul</Label>
              <Input id="changeorderssection-judul" data-testid={CHANGE_ORDERS.titleInput} value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} placeholder="mis. Tambah pekerjaan tangga" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label htmlFor="changeorderssection-delta-nilai-rp">Delta Nilai (Rp)</Label>
                <RupiahInput id="changeorderssection-delta-nilai-rp" data-testid={CHANGE_ORDERS.deltaInput} value={form.value_delta}
                  onChange={(e) => setForm((f) => ({ ...f, value_delta: e.target.value }))} placeholder="+/- IDR" />
              </div>
              <div className="space-y-1.5"><Label htmlFor="changeorderssection-tambah-waktu-hari">Tambah Waktu (hari)</Label>
                <Input id="changeorderssection-tambah-waktu-hari" type="number" data-testid={CHANGE_ORDERS.extInput} value={form.time_extension_days}
                  onChange={(e) => setForm((f) => ({ ...f, time_extension_days: e.target.value }))} placeholder="0" />
              </div>
            </div>
            <div className="space-y-1.5"><Label htmlFor="changeorderssection-alasan-opsional">Alasan (opsional)</Label>
              <Input id="changeorderssection-alasan-opsional" value={form.reason} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>Batal</Button>
            <Button data-testid={CHANGE_ORDERS.save} onClick={create} disabled={busy}>Buat</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
