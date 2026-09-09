import React, { useCallback, useEffect, useState } from "react";
import { Clock, RefreshCw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { P54 } from "@/constants/testIds";

/**
 * SessionBanner — memperingatkan SEBELUM pekerjaan hilang.
 *
 * ## Kenapa spanduk ini ada, dan kenapa ia biasanya TIDAK terlihat
 *
 * Jalur normal Fase 54 tidak melibatkan manusia: `AuthContext` memperpanjang sesi diam-diam
 * beberapa menit sebelum token habis, jadi pemakai tidak pernah tahu ada yang terjadi.
 * Spanduk ini khusus untuk keadaan yang TIDAK bisa diselamatkan diam-diam — misalnya bekal
 * 7 hari sudah benar-benar habis, atau server menolak memperpanjang.
 *
 * Dalam keadaan itu, membiarkan pemakai mengetik terus adalah kekejaman kecil: satu klik
 * "Simpan" berikutnya akan gagal dan isian yang sudah panjang lenyap. Jadi kami mengaku
 * lebih awal: hitung mundur yang jujur, satu tombol untuk mencoba lagi, dan kalimat yang
 * menyebut akibatnya ("selesaikan & simpan") — bukan istilah internal seperti token/JWT.
 */
export default function SessionBanner() {
  const { sessionWarning, renewNow, dismissSessionWarning } = useAuth();
  const [busy, setBusy] = useState(false);
  const [sisa, setSisa] = useState(sessionWarning?.secondsLeft || 0);

  useEffect(() => {
    setSisa(sessionWarning?.secondsLeft || 0);
  }, [sessionWarning]);

  useEffect(() => {
    if (!sessionWarning) return undefined;
    const t = setInterval(() => setSisa((s) => (s > 0 ? s - 1 : 0)), 1000);
    return () => clearInterval(t);
  }, [sessionWarning]);

  const coba = useCallback(async () => {
    setBusy(true);
    try {
      await renewNow();
    } finally {
      setBusy(false);
    }
  }, [renewNow]);

  if (!sessionWarning) return null;

  const menit = Math.floor(sisa / 60);
  const detik = String(Math.max(sisa, 0) % 60).padStart(2, "0");
  const habis = sisa <= 0;

  return (
    <div data-testid={P54.banner}
      className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-amber-300 bg-amber-50 px-4 py-2.5 text-sm text-amber-900 md:px-8">
      <Clock className="h-4 w-4 shrink-0" />
      <p className="flex-1 min-w-[16rem]">
        {habis ? (
          <>Sesi Anda sudah berakhir. <strong>Jangan menutup halaman ini</strong> — coba
            sambungkan ulang, lalu selesaikan &amp; simpan pekerjaan Anda.</>
        ) : (
          <>Sesi Anda akan berakhir dalam{" "}
            <strong data-testid={P54.bannerCountdown}>{menit}:{detik}</strong>. Selesaikan
            &amp; simpan pekerjaan Anda, atau sambungkan ulang sekarang.</>
        )}
      </p>
      <Button data-testid={P54.bannerRenew} size="sm" variant="default"
        disabled={busy} onClick={coba}>
        <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} />
        {busy ? "Menyambungkan…" : "Sambungkan ulang"}
      </Button>
      <button type="button" data-testid={P54.bannerDismiss}
        aria-label="Sembunyikan peringatan sesi"
        onClick={dismissSessionWarning}
        className="rounded-md p-1 text-amber-700 hover:bg-amber-100">
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
