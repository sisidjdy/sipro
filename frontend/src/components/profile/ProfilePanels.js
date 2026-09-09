import React, { useEffect, useState } from "react";
import { History, ShieldCheck } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { PROFILE } from "@/constants/testIds";

const ACTION_LABEL = {
  all: "semua", manage: "kelola", view: "lihat", view_all: "lihat semua", view_own: "lihat sendiri",
  create: "buat", update: "ubah", delete: "hapus", approve: "setujui", assign: "tugaskan",
  sign: "tanda tangan", verify: "verifikasi", override: "terobos", cancel: "batalkan",
};

/** Izin efektif akun ini (dari /auth/me) beserta label resource yang ikut dikirim backend. */
export function MyPermissions() {
  const { user } = useAuth();
  const meta = user?.resource_labels || {};
  const perms = user?.permissions || {};
  const full = !!perms["*"];
  const rows = Object.entries(perms).filter(([k]) => k !== "*").sort();
  return (
    <div className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <h3 className="section-title flex items-center gap-1.5"><ShieldCheck className="h-4 w-4 text-primary" /> Hak akses saya</h3>
      {full ? (
        <p data-testid={PROFILE.permsFull} className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
          Peran Anda berakses penuh ke seluruh modul organisasi ini.
        </p>
      ) : (
        <ul data-testid={PROFILE.permsList} className="max-h-80 space-y-1 overflow-y-auto text-xs">
          {rows.length ? rows.map(([res, acts]) => (
            <li key={res} data-testid={PROFILE.permsItem} data-resource={res} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-b border-border/60 py-1">
              <span className="font-medium">{meta[res] || res}</span>
              <span className="font-mono text-[10px] text-muted-foreground">{res}</span>
              <span className="ml-auto flex flex-wrap gap-1">
                {(acts || []).map((a) => <span key={a} className="rounded border bg-secondary px-1.5 py-0.5 text-[10px]">{ACTION_LABEL[a] || a}</span>)}
              </span>
            </li>
          )) : <li className="text-muted-foreground">Belum ada izin — hubungi admin.</li>}
        </ul>
      )}
      <p className="text-[11px] text-muted-foreground">Izin ditetapkan admin di Hak Akses (RBAC); perubahan berlaku setelah muat ulang.</p>
    </div>
  );
}

export function MyActivity() {
  const [rows, setRows] = useState(null);
  useEffect(() => { api.get("/auth/me/activity").then((r) => setRows(r.data.data)).catch(() => setRows([])); }, []);
  return (
    <div className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <h3 className="section-title flex items-center gap-1.5"><History className="h-4 w-4 text-primary" /> Aktivitas terakhir saya</h3>
      {rows === null ? <p className="text-xs text-muted-foreground">Memuat…</p>
        : !rows.length ? <p data-testid={PROFILE.activityEmpty} className="text-xs text-muted-foreground">Belum ada aktivitas tercatat.</p>
        : (
          <ul data-testid={PROFILE.activityList} className="max-h-80 space-y-1.5 overflow-y-auto text-xs">
            {rows.map((r) => (
              <li key={r.id} data-testid={PROFILE.activityItem} className="flex items-baseline gap-2 border-b border-border/60 py-1">
                <span className="w-32 shrink-0 text-[10px] text-muted-foreground">{formatDateTimeWIB(r.created_at)}</span>
                <span className="font-medium">{ACTION_LABEL[r.action] || r.action}</span>
                <span className="font-mono text-[10px] text-muted-foreground">{r.resource}</span>
                {r.entity_id ? <span className="truncate text-muted-foreground">{String(r.entity_id).slice(0, 18)}</span> : null}
              </li>
            ))}
          </ul>
        )}
    </div>
  );
}
