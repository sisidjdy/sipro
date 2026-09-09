import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CalendarClock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api from "@/services/apiClient";
import { useAuth } from "@/context/AuthContext";
import { P57 } from "@/constants/testIds";

/**
 * SKEMA PEMBAYARAN SATU KONTRAK (Fase 57A). Yang ditolak dengan sengaja: mengganti skema
 * pada kontrak yang uangnya sudah masuk. Menyusun ulang jadwal yang sebagian sudah dibayar
 * berarti menulis ulang kewajiban pembeli tanpa jejak — itu urusan adendum, bukan tombol.
 */
export const ContractSchemePicker = ({ contract, onChanged }) => {
  const { can } = useAuth();
  const plan = contract.payment_plan || {};
  const dipakai = plan.scheme || {};
  const inv = plan.invoice || {};
  const mayAssign = can("payment_scheme", "assign");
  const sudahAdaUang = Number(inv.paid || 0) > 0;

  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState([]);
  const [pilih, setPilih] = useState("");
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await api.get("/payment-schemes", { params: {
        kind: contract.scheme, active: true, project_id: contract.project_id } });
      setRows(res.data.data || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memuat daftar skema.");
    }
  }, [contract.scheme, contract.project_id]);

  useEffect(() => { if (open) load(); }, [open, load]);

  const submit = async () => {
    try {
      await api.post(`/payment-schemes/contracts/${contract.id}`, {
        scheme_id: pilih, reason });
      toast.success("Skema kontrak diperbarui. Aktifkan kontrak untuk menyusun termin.");
      setOpen(false); setReason(""); onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengganti skema.");
    }
  };

  return (
    <div data-testid={P57.contractScheme}
      className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-secondary/30 px-3 py-2 text-xs">
      <span>
        <CalendarClock className="mr-1.5 inline h-3.5 w-3.5" />
        Termin mengikuti skema{" "}
        <strong>{dipakai.name || contract.payment_scheme_name || "—"}</strong>
        {dipakai.source ? (
          <span className="text-muted-foreground"> · asal: {dipakai.source}</span>
        ) : null}
        {dipakai.configurable === false ? (
          <span className="text-amber-700">
            {" "}· belum ada skema tersimpan untuk jenis ini, sistem memakai termin bawaan
          </span>
        ) : null}
      </span>
      {mayAssign ? (
        <Button data-testid={P57.contractSchemeBtn} size="sm" variant="outline"
          onClick={() => setOpen(true)}>
          Ganti skema
        </Button>
      ) : null}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid={P57.contractSchemeDialog} className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Ganti skema pembayaran kontrak</DialogTitle>
            <DialogDescription>
              Hanya skema berjenis <strong>{contract.scheme_label}</strong> yang berlaku di
              proyek ini yang bisa dipilih — jenis menentukan tahap legal &amp; biaya.
              Sesudah diganti, aktifkan kontrak agar termin disusun ulang.
            </DialogDescription>
          </DialogHeader>
          {sudahAdaUang ? (
            <p className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
              Sudah ada penerimaan pada kontrak ini. Mengganti skema akan menyusun ulang
              jadwal yang sebagian sudah dibayar — terbitkan adendum, jangan menimpa jadwal
              berjalan.
            </p>
          ) : (
            <div className="space-y-3">
              <div>
                <Label className="text-xs">Skema</Label>
                <Select value={pilih} onValueChange={setPilih}>
                  <SelectTrigger data-testid={P57.contractSchemeSelect}>
                    <SelectValue placeholder="Pilih skema" />
                  </SelectTrigger>
                  <SelectContent>
                    {rows.map((r) => (
                      <SelectItem key={r.id} value={r.id}>
                        {r.name} · {(r.terms || []).length} termin
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {!rows.length ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Belum ada skema aktif berjenis ini untuk proyek kontrak. Buat dahulu di
                    Pusat Konfigurasi › Skema Pembayaran.
                  </p>
                ) : null}
              </div>
              <div>
                <Label className="text-xs">Alasan penggantian (min. 10 huruf)</Label>
                <Input data-testid={P57.contractSchemeReason} value={reason}
                  placeholder="mis. pembeli minta cicilan 12× sesuai persetujuan manajer"
                  onChange={(e) => setReason(e.target.value)} />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>Tutup</Button>
            <Button data-testid={P57.contractSchemeSubmit} onClick={submit}
              disabled={sudahAdaUang || !pilih || reason.trim().length < 10}>
              Simpan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ContractSchemePicker;
