import React from "react";
import { AlertTriangle, ArrowLeft, RefreshCw, ShieldOff, WifiOff } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { PANELSTATE, WORK } from "@/constants/testIds";

export function LoadingCards({ count = 4 }) {
  return (
    <div data-testid={WORK.loadingState} className="grid gap-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-xl border bg-card p-4">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="mt-2 h-3 w-1/3" />
        </div>
      ))}
    </div>
  );
}

export function LoadingKpis({ count = 5 }) {
  return (
    <div data-testid={WORK.loadingState} className="grid grid-cols-2 gap-3 md:grid-cols-5">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-xl border bg-card p-4">
          <Skeleton className="h-3 w-1/2" />
          <Skeleton className="mt-3 h-6 w-1/3" />
        </div>
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
      <p>{message || "Terjadi kesalahan saat memuat data."}</p>
      {onRetry ? (
        <button data-testid={WORK.retryButton} onClick={onRetry} className="mt-2 rounded-lg border border-rose-300 bg-white px-3 py-1 text-rose-700 hover:bg-rose-100">
          Coba lagi
        </button>
      ) : null}
    </div>
  );
}

/**
 * AccessDenied — satu penjelasan sopan untuk pengguna yang memang tidak berhak.
 *
 * Sebelumnya halaman tetap dirender lalu setiap panel memunculkan pesan teknis
 * backend ("tidak memiliki izin 'view' pada 'construction'") berkali-kali. Itu
 * membocorkan nama izin internal dan membuat pengguna bingung. Sekarang: satu
 * kartu, bahasa manusia, plus jalan keluar yang jelas.
 */
export function AccessDenied({
  title = "Halaman ini bukan untuk peran Anda",
  description = "Anda tidak punya akses ke data ini.",
  askWho = null, backTo = "/", backLabel = "Kembali ke Beranda",
  testId = "access-denied",
}) {
  return (
    <div data-testid={testId}
      className="mx-auto max-w-xl rounded-xl border bg-card p-8 text-center shadow-sm">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-secondary">
        <ShieldOff className="h-6 w-6 text-muted-foreground" />
      </div>
      <p className="mt-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        Akses ditolak
      </p>
      <h2 className="mt-1 font-heading text-lg font-semibold">{title}</h2>
      <p className="mt-1.5 text-sm text-muted-foreground">{description}</p>
      {askWho ? (
        <p className="mt-2 text-xs text-muted-foreground">{askWho}</p>
      ) : null}
      <a href={backTo} data-testid={`${testId}-back`}
        className="mt-5 inline-flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">
        <ArrowLeft className="h-4 w-4" /> {backLabel}
      </a>
    </div>
  );
}

/**
 * PanelDenied — SATU PANEL yang tidak boleh dibuka peran ini (403), sementara halaman di
 * sekitarnya tetap berguna.
 *
 * Bedanya dengan `AccessDenied`: yang itu MENGGANTI halaman (memang seluruh menunya bukan
 * hak peran tersebut), yang ini hanya mengisi badan satu tab. Fase 52 lahir dari cacat
 * nyata: satu 403 panel samping mematikan seluruh halaman profil lead dan menuduh izin yang
 * salah. Kartu ini adalah jawaban jujurnya — halaman hidup, panelnya bercerita.
 *
 * Kalimatnya WAJIB menyebut BAGIAN MANA yang tertutup dan tidak menyebut nama izin internal.
 */
export function PanelDenied({
  subject = "Bagian ini",
  description = null,
  whoMay = null,
  testId = PANELSTATE.denied,
}) {
  return (
    <div data-testid={testId} data-panel-state="denied"
      className="rounded-xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-700">
      <p className="flex items-center gap-2 font-medium text-slate-900">
        <ShieldOff className="h-4 w-4" /> {subject} tidak bisa dibuka dengan peran Anda
      </p>
      <p className="mt-1.5">
        {description || ("Bagian ini sengaja tertutup untuk peran Anda. Isi halaman yang lain "
          + "tetap bisa dipakai seperti biasa — yang tertutup hanya bagian ini.")}
      </p>
      {whoMay ? <p className="mt-1.5 text-xs text-slate-600">{whoMay}</p> : null}
      <p className="mt-1.5 text-xs text-slate-600">
        Ini BUKAN “belum ada data”: datanya mungkin ada, hanya tidak untuk dibaca peran Anda.
      </p>
    </div>
  );
}

/**
 * PanelUnavailable — satu panel yang GAGAL dimuat (5xx/400) atau tidak ada sambungan.
 * Dipisahkan dari `PanelDenied` karena obatnya berbeda: yang ini bisa dicoba lagi.
 */
export function PanelUnavailable({
  subject = "Bagian ini",
  description = null,
  offline = false,
  onRetry = null,
  testId = PANELSTATE.unavailable,
}) {
  const Icon = offline ? WifiOff : AlertTriangle;
  return (
    <div data-testid={testId} data-panel-state={offline ? "offline" : "failed"}
      className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
      <p className="flex items-center gap-2 font-medium">
        <Icon className="h-4 w-4" /> {subject} gagal dimuat
      </p>
      <p className="mt-1.5">
        {description || (offline
          ? "Tidak ada sambungan ke server, jadi bagian ini dibiarkan kosong daripada menampilkan angka lama sebagai kebenaran."
          : "Server tidak mengirim datanya. Bagian ini dibiarkan kosong — bukan berarti datanya tidak ada.")}
      </p>
      {onRetry ? (
        <button type="button" data-testid={PANELSTATE.retry} onClick={onRetry}
          className="mt-2.5 inline-flex items-center gap-1.5 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-amber-900 hover:bg-amber-100">
          <RefreshCw className="h-3.5 w-3.5" /> Coba lagi
        </button>
      ) : null}
    </div>
  );
}

/**
 * PanelStateView — pilih kartu yang BENAR dari hasil `loadPanels()`.
 *
 * Dipakai tab-tab halaman profil: `panel.denied` → PanelDenied, sisanya → PanelUnavailable.
 * Mengembalikan `null` bila panelnya baik-baik saja, supaya pemanggilnya cukup menulis
 * `{stateView || <IsiPanel/>}`.
 */
export function PanelStateView({ panel, subject, whoMay = null, onRetry = null, testId }) {
  if (!panel || panel.ok) return null;
  if (panel.denied) {
    return <PanelDenied subject={subject} whoMay={whoMay}
      testId={testId ? `${testId}-denied` : undefined} />;
  }
  return (
    <PanelUnavailable subject={subject} offline={!!panel.offline} onRetry={onRetry}
      description={panel.detail || undefined}
      testId={testId ? `${testId}-unavailable` : undefined} />
  );
}
