import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Ban, Banknote, FileText, Scale } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import MoneyText from "@/components/patterns/MoneyText";
import StatusPill from "@/components/patterns/StatusPill";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { downloadFile } from "@/utils/fileDownload";
import { formatDateTimeWIB } from "@/utils/formatters";
import { P56 } from "@/constants/testIds";

/**
 * CancellationPanel — PEMBATALAN KONTRAK & REFUND (Fase 56C).
 *
 * Layar untuk janji yang sudah tercetak di dokumen SPR: potongan 35%/50%, pengembalian dana
 * menyusul penjualan ulang unit. Tiga tangan yang berbeda dengan sengaja — dan layar ini
 * TIDAK menyembunyikan tangan yang bukan miliknya, ia MENJELASKANNYA:
 *
 *   • Manajer Sales/Marketing: tombol "Ajukan Pembatalan" (+ pratinjau hitungan);
 *   • Manajer Keuangan: kartu keputusan (setujui/tolak, alasan wajib);
 *   • Keuangan: tombol bayar refund, dengan PENAHANAN yang menyebutkan sebabnya.
 *
 * Aturan kejujuran yang dipegang: hitungan ditampilkan APA ADANYA beserta dasar aturannya
 * (dari Pusat Konfigurasi), dan "belum ada penerimaan" ditulis sebagai kalimat — bukan
 * "refund Rp 0" yang membuat pembeli menyangka sistemnya salah hitung.
 */
export default function CancellationPanel({ contract, onChanged }) {
  const { can, user } = useAuth();
  const mayRequest = can("cancellation", "create");
  const mayDecide = can("cancellation", "approve");
  const mayPay = can("cancellation", "update");
  const mayOverride = can("cancellation", "override");
  const [state, setState] = useState({ loading: true, error: "" });
  const [pre, setPre] = useState(null);
  const [askOpen, setAskOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [decideFor, setDecideFor] = useState(null);
  const [note, setNote] = useState("");
  const [refundFor, setRefundFor] = useState(null);
  const [form, setForm] = useState({ method: "transfer", amount: "", note: "",
    override: false, override_reason: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!contract?.id) return;
    setState({ loading: true, error: "" });
    try {
      const res = await api.get("/cancellations/preview",
        { params: { contract_id: contract.id } });
      setPre(res.data.data);
      setState({ loading: false, error: "" });
    } catch (e) {
      setState({ loading: false,
        error: e?.response?.data?.detail || "Gagal memuat data pembatalan." });
    }
  }, [contract?.id]);

  useEffect(() => { load(); }, [load]);

  const refresh = () => { load(); onChanged && onChanged(); };

  // PDF diambil LEWAT SESI (blob), bukan tautan mentah: endpoint dokumen memakai
  // Authorization header, jadi `window.open(url)` akan menghasilkan 401 di tab baru.
  const openDoc = async (r) => {
    try {
      await downloadFile(`/documents/${r.document_id}/pdf`,
        { fallbackName: r.document_number || "berita-acara-pembatalan", open: true });
    } catch {
      toast.error("Gagal membuka berita acara pembatalan.");
    }
  };

  const submitRequest = async () => {
    setBusy(true);
    try {
      await api.post("/cancellations", { contract_id: contract.id, reason: reason.trim() });
      toast.success("Pengajuan pembatalan dikirim ke Manajer Keuangan.");
      setAskOpen(false); setReason("");
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengajukan pembatalan.");
    } finally { setBusy(false); }
  };

  const submitDecision = async (approved) => {
    setBusy(true);
    try {
      await api.post(`/cancellations/${decideFor.id}/decision`,
        { approved, note: note.trim() });
      toast.success(approved
        ? "Pembatalan disetujui — jurnal potongan & utang refund terbit, unit kembali ke stok."
        : "Pengajuan pembatalan ditolak beralasan.");
      setDecideFor(null); setNote("");
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan keputusan.");
    } finally { setBusy(false); }
  };

  const submitRefund = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/cancellations/${refundFor.id}/refund`, {
        method: form.method,
        amount: form.amount ? Number(String(form.amount).replace(/[^\d]/g, "")) : undefined,
        note: form.note.trim() || undefined,
        // Penanda sekali-pakai: tombol yang ditekan dua kali (atau jaringan yang mengirim
        // ulang) TIDAK boleh melahirkan pembayaran kedua.
        client_ref: `ui-${refundFor.id}-${Date.now()}`,
        override: form.override || undefined,
        override_reason: form.override ? form.override_reason.trim() : undefined,
      });
      toast.success(res.data?.replay
        ? "Pembayaran itu sudah tercatat sebelumnya (tidak dibuat dua kali)."
        : "Refund dibayar & dibukukan.");
      setRefundFor(null);
      setForm({ method: "transfer", amount: "", note: "", override: false,
        override_reason: "" });
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membayar refund.");
    } finally { setBusy(false); }
  };

  if (state.loading || !pre) return null;

  const rows = pre.history || [];
  const berjalan = rows.find((r) => ["diajukan", "disetujui", "refund_sebagian"]
    .includes(r.state));

  return (
    <section data-testid={P56.panel} className="space-y-3 rounded-lg border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="flex items-center gap-2 font-heading text-base font-semibold">
            <Ban className="h-4 w-4" /> Pembatalan & refund
          </h3>
          <p className="text-xs text-muted-foreground">
            Ketentuan pembatalan yang tercetak di SPR dijalankan di sini: potongan dihitung
            dari keadaan pembangunan yang NYATA, sisanya menjadi utang refund yang dibukukan.
          </p>
        </div>
        {mayRequest && pre.can_request ? (
          <Button data-testid={P56.requestBtn} size="sm" variant="outline"
            className="text-rose-600" onClick={() => setAskOpen(true)}>
            <Ban className="mr-1.5 h-3.5 w-3.5" /> Ajukan Pembatalan
          </Button>
        ) : null}
      </div>

      {/* SEBAB belum boleh — bukan tombol mati tanpa penjelasan */}
      {(pre.blocks || []).length ? (
        <div data-testid={P56.blocked}
          className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <p className="flex items-center gap-1.5 font-medium">
            <AlertTriangle className="h-4 w-4" /> Pembatalan belum bisa diajukan
          </p>
          <ul className="mt-1 space-y-0.5 text-xs">
            {pre.blocks.map((b) => <li key={b.code}>• {b.detail}</li>)}
          </ul>
        </div>
      ) : null}

      {!mayRequest && !berjalan ? (
        <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
          Mengajukan pembatalan adalah wewenang Manajer Sales/Marketing — karena itu
          tombolnya tidak ditampilkan untuk peran Anda. Keputusannya sendiri ada pada
          Manajer Keuangan.
        </p>
      ) : null}

      {/* pratinjau hitungan (selalu terlihat: pemakai berhak tahu angkanya sebelum menekan) */}
      {pre.contract ? (
        <div data-testid={P56.preview} className="rounded-lg border bg-background p-3">
          <div className="grid gap-2 text-sm sm:grid-cols-4">
            <div>
              <p className="text-xs text-muted-foreground">Sudah diterima</p>
              <MoneyText value={pre.received_total} className="font-medium" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Potongan ({pre.cut_pct}%)</p>
              <MoneyText value={pre.cut_amount} className="font-medium text-rose-700" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Titipan dikembalikan</p>
              <MoneyText value={pre.deposit_refund} className="font-medium" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Total dikembalikan</p>
              <MoneyText value={pre.payable_total} className="font-semibold text-emerald-700" />
            </div>
          </div>
          <p data-testid={P56.moneyNote} className="mt-2 text-xs text-muted-foreground">
            {pre.note}
          </p>
          <p className="mt-1 flex items-start gap-1.5 text-[11px] text-muted-foreground">
            <Scale className="mt-0.5 h-3 w-3 shrink-0" /> {pre.rule_label}
          </p>
        </div>
      ) : null}

      {/* riwayat pengajuan */}
      {rows.length ? (
        <div className="space-y-2">
          {rows.map((r) => {
            const st = r.settlement || r.basis_at_request || {};
            const payable = r.refund_payable ?? st.payable_total ?? 0;
            const pengaju = r.requested_by === user?.email;
            return (
              <div key={r.id} data-testid={P56.row} data-state={r.state}
                className="space-y-2 rounded-lg border bg-background p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                      <span className="font-mono">{r.number}</span>
                      <span data-testid={P56.stateBadge} data-state={r.state}>
                        <StatusPill status={r.state} group="cancel_state" />
                      </span>
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Diajukan {r.requested_by} · {formatDateTimeWIB(r.requested_at)} · alasan:{" "}
                      {r.reason}
                    </p>
                    {r.decision ? (
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {r.decision.approved ? "Disetujui" : "Ditolak"} {r.decision.by} ·{" "}
                        {formatDateTimeWIB(r.decision.at)} · {r.decision.note}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {r.state === "diajukan" && mayDecide && !pengaju ? (
                      <Button data-testid={P56.decideBtn} size="sm"
                        onClick={() => { setNote(""); setDecideFor(r); }}>
                        Putuskan
                      </Button>
                    ) : null}
                    {r.state === "diajukan" && mayDecide && pengaju ? (
                      <p data-testid={P56.decisionSoD}
                        className="max-w-xs text-xs text-amber-700">
                        Anda yang mengajukan pembatalan ini, jadi keputusannya harus diambil
                        orang lain (aturan empat mata).
                      </p>
                    ) : null}
                    {["disetujui", "refund_sebagian"].includes(r.state) && mayPay
                      && (r.can_pay_refund || mayOverride) ? (
                        <Button data-testid={P56.refundBtn} size="sm" variant="outline"
                          onClick={() => { setForm({ method: "transfer", amount: "", note: "",
                            override: false, override_reason: "" }); setRefundFor(r); }}>
                          <Banknote className="mr-1.5 h-3.5 w-3.5" /> Bayar refund
                        </Button>
                      ) : null}
                    {r.document_id ? (
                      <Button data-testid={P56.docPrint} size="sm" variant="outline"
                        onClick={() => openDoc(r)}>
                        <FileText className="mr-1.5 h-3.5 w-3.5" /> Berita acara
                      </Button>
                    ) : null}
                  </div>
                </div>

                {payable ? (
                  <div className="grid gap-2 border-t pt-2 text-xs sm:grid-cols-3">
                    <p>Utang refund: <MoneyText value={payable} className="font-medium" /></p>
                    <p>Sudah dibayar:{" "}
                      <MoneyText value={r.refund_paid_total || 0} className="font-medium" />
                    </p>
                    <p>Sisa:{" "}
                      <MoneyText value={r.refund_outstanding ?? payable}
                        className="font-medium" />
                    </p>
                  </div>
                ) : null}

                {/* PENAHANAN refund: sebabnya ditulis, bukan tombol yang diam-diam hilang */}
                {r.refund_hold && ["disetujui", "refund_sebagian"].includes(r.state) ? (
                  <p data-testid={P56.refundHold}
                    className="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-2 text-xs text-amber-900">
                    <strong>{r.refund_hold.label}:</strong> {r.refund_hold.detail}
                  </p>
                ) : null}

                {(r.refund_payments || []).map((p) => (
                  <p key={p.id} data-testid={P56.refundPaymentRow}
                    className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <Banknote className="h-3 w-3" />
                    <MoneyText value={p.amount} /> · {p.method_label} · {p.actor} ·{" "}
                    {formatDateTimeWIB(p.at)}
                    {p.override ? (
                      <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] text-violet-900">
                        penahanan diabaikan: {p.override_reason}
                      </span>
                    ) : null}
                  </p>
                ))}

                {(r.journals || []).map((jr) => (
                  <p key={jr.id} data-testid={P56.journalRow}
                    className="text-[11px] text-muted-foreground">
                    Jurnal {jr.entry_no}: {jr.memo} —{" "}
                    {(jr.lines || []).map((ln) => `${ln.account_code} `
                      + `${ln.debit ? "D" : "K"} ${(ln.debit || ln.credit).toLocaleString("id-ID")}`)
                      .join(" · ")}
                  </p>
                ))}
              </div>
            );
          })}
        </div>
      ) : null}

      {/* ---------------- dialog pengajuan ---------------- */}
      <Dialog open={askOpen} onOpenChange={setAskOpen}>
        <DialogContent data-testid={P56.requestDialog} className="max-w-lg bg-background">
          <DialogHeader>
            <DialogTitle>Ajukan pembatalan kontrak {contract?.number}</DialogTitle>
            <DialogDescription>
              Pengajuan ini BELUM mengubah pembukuan. Keputusannya ada pada Manajer Keuangan
              — dan pada saat disetujui, jurnal potongan & utang refund terbit, tagihan yang
              belum dibayar dibatalkan, serta unit kembali ke stok.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="rounded-lg border bg-secondary/40 p-3 text-xs">
              <p>Sudah diterima: <strong>{pre.received_total?.toLocaleString("id-ID")}</strong></p>
              <p>Potongan {pre.cut_pct}%:{" "}
                <strong>{pre.cut_amount?.toLocaleString("id-ID")}</strong></p>
              <p>Yang dikembalikan:{" "}
                <strong>{pre.payable_total?.toLocaleString("id-ID")}</strong></p>
              <p className="mt-1 text-muted-foreground">{pre.rule_label}</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cancel-reason">
                Alasan pembatalan (minimal 10 huruf — dibaca pembeli di berita acara)
              </Label>
              <Textarea id="cancel-reason" data-testid={P56.requestReason} rows={3}
                className="bg-background" value={reason}
                placeholder="mis. pembeli mundur karena pindah tugas ke luar kota"
                onChange={(e) => setReason(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAskOpen(false)}>Batal</Button>
            <Button data-testid={P56.requestSubmit} onClick={submitRequest}
              disabled={busy || reason.trim().length < 10}>
              {busy ? "Mengirim…" : "Ajukan pembatalan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ---------------- dialog keputusan ---------------- */}
      <Dialog open={!!decideFor} onOpenChange={(v) => !v && setDecideFor(null)}>
        <DialogContent data-testid={P56.decideDialog} className="max-w-lg bg-background">
          <DialogHeader>
            <DialogTitle>Putuskan pembatalan {decideFor?.number}</DialogTitle>
            <DialogDescription>
              Menyetujui berarti: potongan{" "}
              {(decideFor?.basis_at_request || {}).cut_pct}% dibukukan sebagai pendapatan
              lain-lain, sisanya menjadi UTANG REFUND kepada pembeli, tagihan yang belum
              dibayar dibatalkan, dan unit kembali ke stok. Menolak pun wajib beralasan —
              pengaju dan pembeli berhak tahu sebabnya.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="rounded-lg border bg-secondary/40 p-3 text-xs">
              <p>Alasan pengaju: {decideFor?.reason}</p>
              <p className="mt-1">{(decideFor?.basis_at_request || {}).note}</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cancel-note">Catatan keputusan (minimal 10 huruf)</Label>
              <Textarea id="cancel-note" data-testid={P56.decideNote} rows={3}
                className="bg-background" value={note}
                onChange={(e) => setNote(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button data-testid={P56.decideReject} variant="outline"
              disabled={busy || note.trim().length < 10}
              onClick={() => submitDecision(false)}>Tolak</Button>
            <Button data-testid={P56.decideApprove}
              disabled={busy || note.trim().length < 10}
              onClick={() => submitDecision(true)}>
              {busy ? "Menyimpan…" : "Setujui pembatalan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ---------------- dialog refund ---------------- */}
      <Dialog open={!!refundFor} onOpenChange={(v) => !v && setRefundFor(null)}>
        <DialogContent data-testid={P56.refundDialog} className="max-w-lg bg-background">
          <DialogHeader>
            <DialogTitle>Bayar refund {refundFor?.number}</DialogTitle>
            <DialogDescription>
              Pembayaran ini menurunkan utang refund (2-1460) dan mengeluarkan kas/bank.
              Boleh dibayar bertahap; sistem menolak nominal yang melebihi sisa.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="rounded-lg border bg-secondary/40 p-3 text-xs">
              <p>Sisa utang refund:{" "}
                <strong>
                  {(refundFor?.refund_outstanding ?? 0).toLocaleString("id-ID")}
                </strong>
              </p>
            </div>
            {refundFor?.refund_hold ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                <p className="font-medium">{refundFor.refund_hold.label}</p>
                <p className="mt-0.5">{refundFor.refund_hold.detail}</p>
                {mayOverride ? (
                  <label className="mt-2 flex items-start gap-2">
                    <Checkbox data-testid={P56.refundOverride} checked={form.override}
                      onCheckedChange={(v) => setForm((f) => ({ ...f, override: !!v }))} />
                    <span>Abaikan penahanan ini (keputusan Manajer Keuangan, tercatat)</span>
                  </label>
                ) : (
                  <p className="mt-2">
                    Hanya Manajer Keuangan yang boleh mengabaikan penahanan ini.
                  </p>
                )}
                {form.override ? (
                  <Textarea data-testid={P56.refundOverrideReason} rows={2}
                    className="mt-2 bg-background"
                    placeholder="Alasan pengabaian (minimal 10 huruf) — dibaca auditor"
                    value={form.override_reason}
                    onChange={(e) => setForm((f) => ({ ...f,
                      override_reason: e.target.value }))} />
                ) : null}
              </div>
            ) : null}
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>Cara pembayaran</Label>
                <Select value={form.method}
                  onValueChange={(v) => setForm((f) => ({ ...f, method: v }))}>
                  <SelectTrigger data-testid={P56.refundMethod} className="bg-background">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="transfer">Transfer bank</SelectItem>
                    <SelectItem value="tunai">Tunai (kas)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="refund-amount">
                  Nominal (kosongkan = seluruh sisa)
                </Label>
                <Input id="refund-amount" data-testid={P56.refundAmount} inputMode="numeric"
                  className="bg-background" value={form.amount}
                  onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="refund-note">Catatan (opsional)</Label>
              <Input id="refund-note" className="bg-background" value={form.note}
                onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRefundFor(null)}>Batal</Button>
            <Button data-testid={P56.refundSubmit} onClick={submitRefund}
              disabled={busy || (form.override && form.override_reason.trim().length < 10)}>
              {busy ? "Menyimpan…" : "Bayar refund"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
