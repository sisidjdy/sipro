import React, { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { PARTNERS } from "@/constants/testIds";

const EFFECT = {
  active: "Mitra boleh menyetor lead & menerima tagihan fee baru.",
  suspended: "Lead & tagihan fee BARU ditolak. Tagihan yang sudah disetujui tetap utang.",
  inactive: "Mitra tidak aktif — lead & fee baru ditolak.",
  expired: "Ditandai kontrak kedaluwarsa — lead & fee baru ditolak sampai kontrak diperbarui.",
  blacklist: "Daftar hitam: lead & fee baru ditolak permanen sampai status diubah kembali.",
};

/**
 * PartnerStatusDialog — ubah status mitra dengan ALASAN WAJIB.
 *
 * Status mitra memblokir uang (lead & fee baru), jadi perubahannya harus punya jejak yang
 * bisa ditunjukkan ke mitra. Backend menolak permintaan tanpa alasan (bukan hanya UI).
 */
export default function PartnerStatusDialog({ partner, open, onOpenChange, onDone }) {
  const [status, setStatus] = useState("active");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) { setStatus(partner?.status || "active"); setReason(""); }
  }, [open, partner]);

  const submit = async () => {
    if (reason.trim().length < 5) {
      toast.error("Alasan wajib diisi (minimal 5 karakter) — status mitra berdampak pada uang.");
      return;
    }
    setBusy(true);
    try {
      await api.post(`/partners/${partner.id}/status`, { status, reason: reason.trim() });
      toast.success(`Status ${partner.name} menjadi ${status}.`);
      onOpenChange(false);
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengubah status mitra.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={PARTNERS.statusDialog}>
        <DialogHeader>
          <DialogTitle>Status Mitra — {partner?.name}</DialogTitle>
          <DialogDescription>
            Status sekarang: <strong>{partner?.status}</strong>. Perubahan dicatat pada riwayat
            mitra beserta alasannya.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Status baru</Label>
            <ReferenceSelect group="agent_status" value={status} onChange={setStatus}
              testId={PARTNERS.statusSelect} />
            <p className="text-xs text-muted-foreground">{EFFECT[status]}</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sreason">Alasan (wajib)</Label>
            <Textarea id="sreason" rows={3} data-testid={PARTNERS.statusReason} value={reason}
              placeholder="Mis. kontrak berakhir dan belum diperpanjang; ada laporan lead palsu…"
              onChange={(e) => setReason(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Batal
          </Button>
          <Button data-testid={PARTNERS.statusSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : "Simpan Status"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
