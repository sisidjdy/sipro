import React, { useState } from "react";
import { toast } from "sonner";
import { Copy, KeyRound, Webhook } from "lucide-react";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import api, { BACKEND_URL } from "@/services/apiClient";
import { PARTNER_HOOK } from "@/constants/testIds";

/**
 * PartnerWebhookCard — pintu masuk lead dari SISTEM MITRA (Fase 43, `docs/v2/25` §4).
 *
 * Kenapa ini ada: mitra aggregator & kantor broker punya sistemnya sendiri. Sebelum ini
 * satu-satunya cara memasukkan leadnya adalah mengetik ulang secara manual, jadi atribusi
 * mitra bergantung pada ingatan orang — dan setiap lead yang lupa ditandai berubah menjadi
 * sengketa fee. Token diberikan PER MITRA supaya sumber setiap lead bisa dibuktikan dan bisa
 * dicabut tanpa mengganggu mitra lain.
 *
 * Token penuh hanya ditampilkan SEKALI (saat diterbitkan). Setelah itu layar hanya menampilkan
 * 4 karakter terakhir sebagai penanda — token yang bisa dibaca ulang kapan saja sama saja
 * dengan menyimpan kunci di bawah keset.
 */
export default function PartnerWebhookCard({ partner, webhook, canManage, onDone }) {
  const [token, setToken] = useState(null);
  const [busy, setBusy] = useState(false);
  const url = `${BACKEND_URL}${webhook?.path || `/api/webhooks/partner/${partner?.id}`}`;

  const rotate = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/partners/${partner.id}/webhook-token`);
      setToken(res.data.data);
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menerbitkan token webhook.");
    } finally { setBusy(false); }
  };

  const copy = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Disalin ke papan klip.");
    } catch {
      toast.error("Peramban menolak menyalin — salin manual dari kotak di atas.");
    }
  };

  return (
    <div data-testid={PARTNER_HOOK.card} className="rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
      <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <Webhook className="h-4 w-4 text-primary" /> Webhook Lead
        {webhook?.enabled ? (
          <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-xs text-emerald-700">
            aktif · {webhook.hint}
          </span>
        ) : (
          <span className="rounded bg-secondary px-1.5 py-0.5 text-xs text-muted-foreground">
            belum ada token
          </span>
        )}
      </h3>
      <p className="text-xs text-muted-foreground">
        Mitra mengirim <code>POST</code> JSON (minimal <code>phone</code>; boleh disertai
        {" "}<code>name</code>, <code>email</code>, <code>campaign</code>, <code>message</code>)
        dengan header <code>{webhook?.header || "X-Partner-Token"}</code>.
      </p>
      <p data-testid={PARTNER_HOOK.url}
        className="mt-2 break-all rounded border bg-secondary/50 p-2 font-mono text-xs">
        {url}
      </p>
      <p className="mt-2 text-xs text-muted-foreground">
        Nomor yang sudah ada di CRM tidak akan menjadi lead kembar: klaimnya dicatat dan
        pemenang atribusinya ditentukan mesin atribusi mitra (first/last touch sesuai Pusat
        Konfigurasi). Mitra yang ditangguhkan atau kontraknya habis DITOLAK.
      </p>
      {canManage ? (
        <Button size="sm" variant="outline" className="mt-3" data-testid={PARTNER_HOOK.rotate}
          onClick={rotate} disabled={busy}>
          <KeyRound className="mr-1.5 h-4 w-4" />
          {busy ? "Menerbitkan…" : (webhook?.enabled ? "Terbitkan ulang token" : "Terbitkan token")}
        </Button>
      ) : null}

      <Dialog open={!!token} onOpenChange={(v) => !v && setToken(null)}>
        <DialogContent data-testid={PARTNER_HOOK.dialog}>
          <DialogHeader>
            <DialogTitle>Token webhook — {partner?.name}</DialogTitle>
            <DialogDescription>
              Simpan sekarang. Token penuh TIDAK ditampilkan lagi; token lama sudah tidak
              berlaku sejak detik ini.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <p data-testid={PARTNER_HOOK.token}
              className="break-all rounded border bg-secondary/50 p-2 font-mono text-xs">
              {token?.token}
            </p>
            <p className="text-xs text-muted-foreground">{token?.note}</p>
            <Button size="sm" variant="secondary"
              onClick={() => copy(`${url}\n${token?.header}: ${token?.token}`)}>
              <Copy className="mr-1.5 h-4 w-4" /> Salin URL + token
            </Button>
          </div>
          <DialogFooter>
            <Button onClick={() => setToken(null)}>Sudah saya simpan</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
