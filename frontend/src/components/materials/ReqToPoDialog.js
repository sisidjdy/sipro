import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ShoppingCart, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { formatIDR } from "@/utils/formatters";
import api from "@/services/apiClient";
import { REQPO as T } from "@/constants/testIds";

/**
 * ReqToPoDialog (Fase 48B) — mengubah KEKURANGAN permintaan material menjadi PO.
 *
 * Jalur yang sebelumnya tidak ada: permintaan yang disetujui hanya bisa “keluarkan dari
 * stok”, sehingga saat stok kurang pembelian lahir tanpa jejak ke lapangan. Dialog ini
 * menampilkan kekurangan yang DIHITUNG SERVER (diminta − keluar − stok − sudah dipesan) dan
 * mengusulkan harga acuan dari daftar harga vendor — harga tidak pernah ditebak sistem.
 */
export default function ReqToPoDialog({ requisition, onOpenChange, onDone }) {
  const [shortage, setShortage] = useState(null);
  const [vendors, setVendors] = useState([]);
  const [vendorId, setVendorId] = useState("");
  const [prices, setPrices] = useState({});
  const [due, setDue] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!requisition) { setShortage(null); return; }
    try {
      const [s, v] = await Promise.all([
        api.get(`/materials/requisitions/${requisition.id}/shortage`),
        api.get("/vendors", { params: { active: true } }),
      ]);
      setShortage(s.data.data);
      setVendors(v.data.data || []);
      const draft = {};
      (s.data.data.rows || []).forEach((r) => {
        if (r.shortage > 0) draft[r.material_id] = r.reference_price || "";
      });
      setPrices(draft);
      setVendorId(""); setDue("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menghitung kekurangan.");
    }
  }, [requisition]);

  useEffect(() => { load(); }, [load]);

  const rows = (shortage?.rows || []).filter((r) => r.shortage > 0);
  const total = rows.reduce(
    (sum, r) => sum + (Number(prices[r.material_id]) || 0) * r.shortage, 0);

  const submit = async () => {
    if (!vendorId) { toast.error("Pilih vendor."); return; }
    const items = rows.map((r) => ({
      material_id: r.material_id, qty: r.shortage,
      unit_price: Math.round(Number(prices[r.material_id]) || 0),
    }));
    if (items.some((i) => !i.unit_price)) {
      toast.error("Isi harga satuan setiap item — sistem tidak mengarang harga."); return;
    }
    setBusy(true);
    try {
      const r = await api.post(`/materials/requisitions/${requisition.id}/to-po`, {
        vendor_id: vendorId, items, due_date: due || null,
      });
      const warn = (r.data.price_checks || []).filter((c) => c.state === "di_atas_acuan");
      toast.success(`PO ${r.data.data.po_number} dibuat dari permintaan `
        + `${requisition.req_number} — menunggu persetujuan.`);
      if (warn.length) {
        toast.warning(`${warn.length} item di atas harga acuan: ${warn[0].detail}`);
      }
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membuat PO.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={!!requisition} onOpenChange={onOpenChange}>
      <DialogContent data-testid={T.dialog} className="max-h-[88vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Buat PO dari kekurangan stok</DialogTitle>
          <DialogDescription>
            {requisition?.req_number} · {requisition?.purpose || "Permintaan material"}
          </DialogDescription>
        </DialogHeader>

        {!shortage ? <p className="text-sm text-muted-foreground">Menghitung kekurangan…</p>
          : !rows.length ? (
            <p className="rounded-lg border border-dashed bg-secondary/40 p-3 text-sm text-muted-foreground">
              {shortage.detail}
              {(shortage.po_numbers || []).length
                ? ` PO terkait: ${shortage.po_numbers.join(", ")}.` : ""}
            </p>
          ) : (
            <div className="space-y-3">
              <div data-testid={T.shortageBox} className="space-y-2">
                {rows.map((r) => (
                  <div key={r.material_id} data-testid={T.shortageRow}
                    className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
                    <div className="flex items-center justify-between text-sm">
                      <div>
                        <p className="font-medium">{r.name}</p>
                        <p className="text-[11px] text-muted-foreground">
                          diminta {r.qty_requested} · stok {r.stock} · sudah dipesan {r.qty_po}
                          {" "}→ <b>kurang {r.shortage} {r.uom}</b>
                        </p>
                      </div>
                      <div className="w-36">
                        <Label htmlFor={`harga-satuan-${r.code}`} className="text-[11px]">
                          Harga satuan</Label>
                        <RupiahInput id={`harga-satuan-${r.code}`} data-testid={T.price} className="h-8" value={prices[r.material_id] ?? ""}
                          onChange={(e) => setPrices((p) => ({
                            ...p, [r.material_id]: e.target.value }))} />
                      </div>
                    </div>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      {r.reference_price
                        ? `Harga acuan ${formatIDR(r.reference_price)} — ${r.reference_basis}.`
                        : "Belum ada harga acuan untuk material ini — isi harga dari penawaran vendor."}
                    </p>
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>Vendor</Label>
                  <Select value={vendorId} onValueChange={setVendorId}>
                    <SelectTrigger data-testid={T.vendorSelect}>
                      <SelectValue placeholder={vendors.length ? "Pilih vendor…"
                        : "Belum ada vendor terdaftar"} /></SelectTrigger>
                    <SelectContent>
                      {vendors.map((v) => (
                        <SelectItem key={v.id} value={v.id}>{v.name} ({v.code})</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="reqpo-due">Jatuh tempo kirim</Label>
                  <Input id="reqpo-due" data-testid={T.due} type="date" value={due}
                    onChange={(e) => setDue(e.target.value)} />
                </div>
              </div>

              <div className="rounded-lg bg-secondary p-3 text-sm">
                Total PO: <span className="font-semibold tabular-nums">{formatIDR(total)}</span>
              </div>
              {!vendors.length ? (
                <p className="flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
                  <TriangleAlert className="mt-0.5 h-3.5 w-3.5" />
                  Daftarkan vendor lebih dulu di Pengadaan → Vendor supaya PO tidak menyebut
                  vendor sebagai teks bebas.
                </p>
              ) : null}
            </div>
          )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Tutup</Button>
          <Button data-testid={T.submit} onClick={submit}
            disabled={busy || !rows.length || !vendors.length}>
            <ShoppingCart className="mr-1.5 h-4 w-4" />
            {busy ? "Membuat PO…" : "Buat PO"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
