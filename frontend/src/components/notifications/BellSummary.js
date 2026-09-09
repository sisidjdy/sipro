import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Bell, Inbox } from "lucide-react";

import {
  DropdownMenu, DropdownMenuContent, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { CATEGORY_ICON, CATEGORY_TONE } from "@/components/notifications/NotificationRows";
import { fromNow } from "@/utils/formatters";
import { cn } from "@/lib/utils";
import api from "@/services/apiClient";
import { NAV } from "@/constants/testIds";

/** Lonceng TopBar: klik = ringkasan notifikasi; detail lengkap ada di /notifications. */
export default function BellSummary({ unread, onUnread }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const load = async () => {
    setLoading(true); setError(false);
    try {
      const r = await api.get("/notifications", { params: { limit: 6, group: true } });
      setRows(r.data.data || []);
      setSummary(r.data.summary || null);
      if (typeof r.data.unread === "number") onUnread?.(r.data.unread);
    } catch { setError(true); } finally { setLoading(false); }
  };

  const goAll = () => { setOpen(false); navigate("/notifications"); };
  const cats = Object.entries(summary?.per_category || {}).filter(([, n]) => n > 0);

  return (
    <DropdownMenu open={open} onOpenChange={(v) => { setOpen(v); if (v) load(); }}>
      <DropdownMenuTrigger asChild>
        <button data-testid={NAV.notifBell} aria-label="Notifikasi"
          className="relative rounded-lg p-2 transition-colors hover:bg-secondary">
          <Bell className="h-5 w-5" />
          {unread > 0 ? (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-destructive-foreground">
              {unread > 9 ? "9+" : unread}
            </span>
          ) : null}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" data-testid="notif-bell-menu" className="w-[360px] p-0">
        <div className="border-b px-3 py-2.5">
          <p className="font-heading text-sm font-semibold">Notifikasi</p>
          <p data-testid="notif-bell-summary" className="text-xs text-muted-foreground">
            {error ? "Gagal memuat ringkasan — coba buka lagi."
              : summary
                ? `${summary.unread} belum dibaca · ${summary.needs_action} perlu tindakan`
                : "Memuat ringkasan…"}
          </p>
          {cats.length ? (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {cats.map(([c, n]) => (
                <span key={c}
                  className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium capitalize",
                    CATEGORY_TONE[c] || CATEGORY_TONE.sistem)}>
                  {c} {n}
                </span>
              ))}
            </div>
          ) : null}
        </div>
        <div className="max-h-[320px] overflow-y-auto">
          {loading && !rows.length ? (
            <p className="px-3 py-4 text-sm text-muted-foreground">Memuat…</p>
          ) : !rows.length ? (
            <div className="flex flex-col items-center gap-1 px-3 py-6 text-muted-foreground">
              <Inbox className="h-5 w-5" />
              <p className="text-sm">Tidak ada notifikasi.</p>
            </div>
          ) : rows.map((n) => {
            const Icon = CATEGORY_ICON[n.category] || Bell;
            return (
              <button key={n.id} data-testid="notif-bell-row" type="button"
                onClick={() => { setOpen(false); navigate(n.link || "/notifications"); }}
                className="flex w-full items-start gap-2.5 border-b px-3 py-2 text-left transition-colors last:border-b-0 hover:bg-secondary">
                <span className={cn("mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
                  CATEGORY_TONE[n.category] || CATEGORY_TONE.sistem)}>
                  <Icon className="h-3.5 w-3.5" />
                </span>
                <span className="min-w-0">
                  <span className={cn("block truncate text-sm",
                    n.read ? "text-muted-foreground" : "font-medium")}>
                    {n.count > 1 ? `${n.count}× ` : ""}{n.title}
                  </span>
                  {n.body ? (
                    <span className="block truncate text-xs text-muted-foreground">{n.body}</span>
                  ) : null}
                  <span className="block text-[10px] text-muted-foreground">
                    {fromNow(n.created_at)}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
        <div className="border-t p-2">
          <Button size="sm" variant="secondary" className="w-full"
            data-testid="notif-bell-open-page" onClick={goAll}>
            Buka halaman notifikasi <ArrowRight className="ml-1 h-3.5 w-3.5" />
          </Button>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
