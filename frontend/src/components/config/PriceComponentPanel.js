import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Pencil } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import DataTable from "@/components/patterns/DataTable";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { useReference } from "@/context/ReferenceContext";
import { formatIDR } from "@/utils/formatters";
import { CONFIG } from "@/constants/testIds";

/**
 * Komponen biaya per skema pembayaran (keputusan owner D12: tiap tipe pembayaran punya
 * komponen berbeda, KPR paling banyak) + perlakuan keuangannya yang menentukan jurnal.
 */
export default function PriceComponentPanel() {
  const { labelOf } = useReference();
  const [matrix, setMatrix] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState({ q: "", sort: "code", direction: "asc", skip: 0, limit: 50 });
  const [form, setForm] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [m, list] = await Promise.all([
        api.get("/catalog/price-components/matrix"),
        api.get("/catalog/price-components"),
      ]);
      setMatrix(m.data.data);
      setRows(list.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat komponen biaya.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    try {
      await api.put(`/catalog/price-components/${form.id}`, {
        label: form.label, value: Number(form.value) || 0,
        finance_treatment: form.finance_treatment, gl_account: form.gl_account || null,
        applies_schemes: form.applies_schemes || [], note: form.note || null,
      });
      toast.success("Komponen biaya diperbarui.");
      setForm(null); load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan.");
    }
  };

  const schemes = matrix?.schemes || [];
  const toggleScheme = (value) => setForm((f) => {
    const set = new Set(f.applies_schemes || []);
    if (set.has(value)) set.delete(value); else set.add(value);
    return { ...f, applies_schemes: [...set] };
  });

  const columns = [
    { key: "code", header: "Kode", sortable: true,
      render: (r) => <span className="font-mono text-xs">{r.code}</span> },
    { key: "label", header: "Komponen", sortable: true,
      render: (r) => (
        <div>
          <div className="font-medium">{r.label}</div>
          {r.note ? <div className="text-xs text-muted-foreground">{r.note}</div> : null}
        </div>
      ) },
    { key: "group", header: "Kelompok", sortable: true,
      render: (r) => labelOf("price_component_group", r.group) },
    { key: "finance_treatment", header: "Perlakuan keuangan", sortable: true,
      render: (r) => (
        <div>
          <div>{labelOf("finance_treatment", r.finance_treatment)}</div>
          <div className="font-mono text-[10px] text-muted-foreground">{r.gl_account || "-"}</div>
        </div>
      ),
      exportValue: (r) => r.finance_treatment },
    { key: "value", header: "Nilai bawaan", align: "right",
      render: (r) => (r.value ? formatIDR(r.value) : "—"), exportValue: (r) => r.value },
    ...schemes.map((s) => ({
      key: `scheme_${s.value}`, header: s.label,
      render: (r) => {
        const on = !(r.applies_schemes || []).length || (r.applies_schemes || []).includes(s.value);
        return <span className={on ? "font-medium text-primary" : "text-muted-foreground"}>
          {on ? "Ya" : "–"}
        </span>;
      },
      exportValue: (r) => ((!(r.applies_schemes || []).length
        || (r.applies_schemes || []).includes(s.value)) ? "ya" : "tidak"),
    })),
    { key: "actions", header: "Aksi", align: "right", sticky: true, sticky: true,
      render: (r) => (
        <Button data-testid={CONFIG.priceEdit} size="sm" variant="ghost"
          onClick={() => setForm({ ...r })}>
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      ), exportValue: () => "" },
  ];

  return (
    <div data-testid={CONFIG.pricePanel} className="space-y-3">
      <div className="rounded-md border bg-secondary p-3 text-sm">
        <strong>Perlakuan keuangan</strong> menentukan jurnal: <em>Pendapatan</em> masuk penjualan,
        <em> Titipan pelanggan</em> (BPHTB/notaris/biaya bank) tidak diakui sebagai pendapatan,
        <em> Potongan</em> mengurangi penjualan, <em>Informasi</em> hanya keterangan (mis. plafon KPR).
        Ubah di sini bila kebijakan akuntansi berbeda — tidak perlu ubah kode.
      </div>
      <DataTable
        testId="config-price-table"
        testIds={{ search: "config-price-search", row: CONFIG.priceRow,
          export: "config-price-export", columns: "config-price-columns" }}
        columns={columns} rows={rows} total={rows.length} query={query}
        onQueryChange={(p) => setQuery((q) => ({ ...q, ...p }))}
        loading={loading} error={error} onRefresh={load}
        searchPlaceholder="Cari komponen biaya…" exportName="komponen-biaya"
        emptyTitle="Belum ada komponen biaya" />

      <Dialog open={!!form} onOpenChange={(o) => { if (!o) setForm(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ubah komponen biaya</DialogTitle>
            <DialogDescription>{form?.code}</DialogDescription>
          </DialogHeader>
          {form ? (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="pc-label">Nama komponen</Label>
                <Input id="pc-label" value={form.label}
                  onChange={(e) => setForm({ ...form, label: e.target.value })} />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="pc-value">Nilai bawaan (Rp)</Label>
                  <RupiahInput id="pc-value" data-testid={CONFIG.priceFormValue}
                    value={form.value || 0}
                    onChange={(e) => setForm({ ...form, value: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label>Akun GL</Label>
                  <ReferenceSelect group="gl_account" value={form.gl_account || ""}
                    testId={CONFIG.priceFormAccount} placeholder="Pilih akun dari bagan akun…"
                    onChange={(v) => setForm({ ...form, gl_account: v })} />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>Perlakuan keuangan</Label>
                <ReferenceSelect group="finance_treatment" value={form.finance_treatment}
                  testId={CONFIG.priceFormTreatment}
                  onChange={(v) => setForm({ ...form, finance_treatment: v })} />
              </div>
              <div className="space-y-1.5">
                <Label>Berlaku pada skema bayar</Label>
                <div className="flex flex-wrap gap-3 rounded-md border bg-secondary p-2">
                  {schemes.map((s) => (
                    <label key={s.value} className="flex items-center gap-2 text-sm">
                      <input type="checkbox"
                        checked={(form.applies_schemes || []).includes(s.value)}
                        onChange={() => toggleScheme(s.value)} />
                      {s.label}
                    </label>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  Kosongkan semua = berlaku untuk semua skema.
                </p>
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setForm(null)}>Batal</Button>
            <Button data-testid={CONFIG.priceSubmit} onClick={submit}>Simpan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
