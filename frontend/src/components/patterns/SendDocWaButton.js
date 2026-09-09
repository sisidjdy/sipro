import React, { useState } from "react";
import { toast } from "sonner";
import { Send, Copy, ExternalLink, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import api from "@/services/apiClient";
import { P62 } from "@/constants/testIds";

/**
 * SendDocWaButton — kirim dokumen ke WhatsApp pihak luar (Fase 62).
 *
 * Subkontraktor & vendor tidak punya akun di sistem ini, jadi SPK/PO/berita acara selalu
 * berpindah lewat WhatsApp. Tombol ini menerbitkan TAUTAN BERBATAS WAKTU ke dokumennya dan
 * menyiapkan pesan siap kirim; yang menekan "kirim" tetap manusia. Nomor tujuan diambil
 * dari master (subkontraktor/vendor/pembeli) — bila belum ada, layar mengatakannya dan
 * pesan tetap bisa dikirim ke nomor mana pun lewat WhatsApp.
 */
export default function SendDocWaButton({ kind, id, label = "Kirim via WhatsApp",
  variant = "outline" }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [share, setShare] = useState(null);

  const buat = async () => {
    setBusy(true);
    try {
      const res = await api.post("/docs/share", { kind, id });
      setShare(res.data.data);
      setOpen(true);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyiapkan pengiriman dokumen.");
    } finally { setBusy(false); }
  };

  const salin = async () => {
    try {
      await navigator.clipboard.writeText(share.url);
      toast.success("Tautan dokumen disalin.");
    } catch { toast.error("Tautan tidak bisa disalin — pilih teksnya secara manual."); }
  };

  return (
    <>
      <Button size="sm" variant={variant} data-testid={P62.sendWaBtn} disabled={busy}
        onClick={buat}>
        <Send className="mr-1.5 h-4 w-4" /> {busy ? "Menyiapkan…" : label}
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid={P62.sendWaDialog} className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Kirim {share?.doc_number || "dokumen"} via WhatsApp</DialogTitle>
            <DialogDescription>
              Tautan berlaku terbatas dan bisa dicabut. Dokumen yang dibuka penerima selalu
              versi terkini — tidak ada berkas basi yang beredar.
            </DialogDescription>
          </DialogHeader>

          {share ? (
            <div className="space-y-3">
              <div className="rounded-lg border bg-secondary/40 p-3 text-[12px]">
                <p><b>Kepada:</b> {share.to_name || "—"}{" "}
                  {share.phone_known ? `· ${share.to_phone}` : ""}</p>
                <p className="mt-1 break-all"><b>Tautan:</b> {share.url}</p>
                <p className="mt-1 text-muted-foreground">
                  Berlaku sampai {String(share.expires_at || "").slice(0, 10)}
                </p>
              </div>

              {!share.phone_known ? (
                <p data-testid={P62.sendWaNoPhone}
                  className="flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-[12px] text-amber-900">
                  <ShieldAlert className="mt-0.5 h-3.5 w-3.5" />
                  Nomor WhatsApp penerima belum tercatat di master. Pesan tetap bisa dikirim —
                  WhatsApp akan meminta Anda memilih kontaknya.
                </p>
              ) : null}

              <Textarea readOnly rows={7} value={share.message || ""}
                aria-label="Pesan WhatsApp yang akan dikirim" className="text-[12px]" />

              <div className="flex flex-wrap gap-2">
                <Button asChild data-testid={P62.sendWaLink}>
                  <a href={share.wa_url} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="mr-1.5 h-4 w-4" /> Buka WhatsApp
                  </a>
                </Button>
                <Button variant="outline" data-testid={P62.sendWaCopy} onClick={salin}>
                  <Copy className="mr-1.5 h-4 w-4" /> Salin tautan
                </Button>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
