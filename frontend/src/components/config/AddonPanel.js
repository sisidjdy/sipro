import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Pencil, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import DataTable from "@/components/patterns/DataTable";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { useReference } from "@/context/ReferenceContext";
import { formatIDR } from "@/utils/formatters";
import { CONFIG } from "@/constants/testIds";

const EMPTY = {
  code: "", name: "", category: "spek_bangunan", pricing_mode: "lump_sum", unit_price: 0,
  uom: "unit", finance_treatment: "revenue", gl_account: "4-1100", negotiable: false,
  active: true, requires_document: "", note: "",
};

/**
 * Master SPEK TAMBAHAN / ADD-ON (permintaan owner): spek bangunan, lahan lebih, hook, dll.
 * Dipilih saat reservasi/booking dan di finance menjadi KOMPONEN TERPISAH (bukan dilebur
 * ke harga unit) supaya pendapatan inti vs tambahan bisa dipisah di laporan.
 */
export default function AddonPanel() {
  const { labelOf } = useReference();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState({ q: "", sort: "code", direction: "asc", skip: 0, limit: 50 });
  const [category, setCategory] = useState("");
  const [form, setForm] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await api.get("/catalog/addons", {
        params: { category: category || undefined },
      });
      setRows(res.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat add-on.");
    } finally { setLoading(false); }
  }, [category]);

  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    try {
      const body = { ...form, unit_price: Number(form.unit_price) || 0 };
      if (form.id) {
        const { id, code, created_at, updated_at, org_id, ...patch } = body;
        await api.put(`/catalog/addons/${form.id}`, patch);
      } else {
        await api.post("/catalog/addons", body);
      }
      toast.success("Add-on disimpan.");
      setForm(null); load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan add-on.");
    }
  };

  const filtered = rows.filter((r) => {
    const q = (query.q || "").toLowerCase();
    return !q || `${r.code} ${r.name}`.toLowerCase().includes(q);
  });

  const columns = [
    { key: "code", header: "Kode", sortable: true,
      render: (r) => <span className="font-mono text-xs">{r.code}</span> },
    { key: "name", header: "Spek tambahan", sortable: true,
      render: (r) => (
        <div>
          <div className="font-medium">{r.name}</div>
          {r.requires_document ? (
            <div className="text-xs text-amber-700">Wajib dokumen: {r.requires_document}</div>
          ) : null}
          {r.note ? <div className="text-xs text-muted-foreground">{r.note}</div> : null}
        </div>
      ) },
    { key: "category", header: "Kategori", sortable: true,
      render: (r) => labelOf("addon_category", r.category) },
    { key: "pricing_mode", header: "Cara hitung", sortable: true,
      render: (r) => labelOf("addon_pricing_mode", r.pricing_mode) },
    { key: "unit_price", header: "Harga", align: "right", sortable: true,
      render: (r) => (r.unit_price
        ? <span>{formatIDR(r.unit_price)}<span className="text-xs text-muted-foreground">
          {r.pricing_mode === "per_m2" ? " /m²" : ""}</span></span>
        : <span className="text-muted-foreground">belum diisi</span>),
      exportValue: (r) => r.unit_price },
    { key: "finance_treatment", header: "Perlakuan keuangan",
      render: (r) => labelOf("finance_treatment", r.finance_treatment),
      exportValue: (r) => r.finance_treatment },
    { key: "negotiable", header: "Nego",
      render: (r) => (r.negotiable ? "Boleh nego" : "Harga tetap"),
      exportValue: (r) => (r.negotiable ? "ya" : "tidak") },
    { key: "actions", header: "Aksi", align: "right", sticky: true,
      render: (r) => (
        <Button data-testid={CONFIG.addonEdit} size="sm" variant="ghost"
          onClick={() => setForm({ ...EMPTY, ...r })}>
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      ), exportValue: () => "" },
  ];

  return (
    <div data-testid={CONFIG.addonPanel} className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Daftar awal ini sengaja kasar — tambahkan spek Anda sendiri beserta harganya.
          Add-on “Kelebihan tanah” otomatis diusulkan bila unit punya luas lebih.
        </p>
        <Button data-testid={CONFIG.addonAdd} size="sm" onClick={() => setForm({ ...EMPTY })}>
          <Plus className="mr-1.5 h-4 w-4" /> Add-on baru
        </Button>
      </div>
      <DataTable
        testId="config-addon-table"
        testIds={{ search: "config-addon-search", row: CONFIG.addonRow,
          export: "config-addon-export", columns: "config-addon-columns" }}
        columns={columns} rows={filtered} total={filtered.length} query={query}
        onQueryChange={(p) => setQuery((q) => ({ ...q, ...p }))}
        loading={loading} error={error} onRefresh={load}
        searchPlaceholder="Cari add-on…" exportName="spek-tambahan"
        emptyTitle="Belum ada add-on"
        filters={(
          <div className="w-[200px]">
            <ReferenceSelect group="addon_category" value={category} allowEmpty
              emptyLabel="Semua kategori" testId="config-addon-filter-category"
              onChange={setCategory} />
          </div>
        )} />

      <Dialog open={!!form} onOpenChange={(o) => { if (!o) setForm(null); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{form?.id ? "Ubah add-on" : "Add-on baru"}</DialogTitle>
            <DialogDescription>
              Add-on menjadi baris terpisah pada SPR, kontrak, tagihan, dan jurnal.
            </DialogDescription>
          </DialogHeader>
          {form ? (
            <div className="max-h-[60vh] space-y-3 overflow-y-auto pr-1">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="ad-code">Kode</Label>
                  <Input id="ad-code" data-testid={CONFIG.addonFormCode} value={form.code}
                    disabled={!!form.id} placeholder="ADD-KANOPI"
                    onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="ad-name">Nama</Label>
                  <Input id="ad-name" data-testid={CONFIG.addonFormName} value={form.name}
                    placeholder="Kanopi carport"
                    onChange={(e) => setForm({ ...form, name: e.target.value })} />
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>Kategori</Label>
                  <ReferenceSelect group="addon_category" value={form.category}
                    testId={CONFIG.addonFormCategory}
                    onChange={(v) => setForm({ ...form, category: v })} />
                </div>
                <div className="space-y-1.5">
                  <Label>Cara hitung harga</Label>
                  <ReferenceSelect group="addon_pricing_mode" value={form.pricing_mode}
                    testId={CONFIG.addonFormMode}
                    onChange={(v) => setForm({ ...form, pricing_mode: v })} />
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="ad-price">Harga (Rp)</Label>
                  <RupiahInput id="ad-price" data-testid={CONFIG.addonFormPrice}
                    value={form.unit_price}
                    onChange={(e) => setForm({ ...form, unit_price: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label>Satuan</Label>
                  <ReferenceSelect group="uom" value={form.uom} testId="config-addon-form-uom"
                    onChange={(v) => setForm({ ...form, uom: v })} />
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>Perlakuan keuangan</Label>
                  <ReferenceSelect group="finance_treatment" value={form.finance_treatment}
                    testId={CONFIG.addonFormTreatment}
                    onChange={(v) => setForm({ ...form, finance_treatment: v })} />
                </div>
                <div className="space-y-1.5">
                  <Label>Akun GL</Label>
                  <ReferenceSelect group="gl_account" value={form.gl_account || ""}
                    testId="config-addon-form-account" placeholder="Pilih akun dari bagan akun…"
                    onChange={(v) => setForm({ ...form, gl_account: v })} />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ad-doc">Dokumen wajib (kode)</Label>
                <Input id="ad-doc" value={form.requires_document || ""} placeholder="SPKT"
                  onChange={(e) => setForm({ ...form, requires_document: e.target.value })} />
              </div>
              <div className="flex flex-wrap items-center gap-6">
                <div className="flex items-center gap-2">
                  <Switch checked={!!form.negotiable} aria-label="Boleh nego"
                    onCheckedChange={(v) => setForm({ ...form, negotiable: v })} />
                  <span className="text-sm">Boleh nego (harga disepakati per unit)</span>
                </div>
                <div className="flex items-center gap-2">
                  <Switch checked={!!form.active} aria-label="Aktif"
                    onCheckedChange={(v) => setForm({ ...form, active: v })} />
                  <span className="text-sm">Aktif</span>
                </div>
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setForm(null)}>Batal</Button>
            <Button data-testid={CONFIG.addonSubmit} onClick={submit}
              disabled={!form?.code || !form?.name}>Simpan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
