import React, { useEffect, useState, useCallback, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { LogOut, ChevronDown, Menu, Building2, Check, UserCircle2, FlaskConical } from "lucide-react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import BellSummary from "@/components/notifications/BellSummary";
import { PAGE_META } from "@/config/navigationConfig";
import { useAuth } from "@/context/AuthContext";
import { roleLabel, initials } from "@/utils/formatters";
import api, { API, TOKEN_KEY } from "@/services/apiClient";
import { NAV, AUTH, PROFILE } from "@/constants/testIds";

function resolveMeta(pathname) {
  if (PAGE_META[pathname]) return PAGE_META[pathname];
  const match = Object.keys(PAGE_META).find((k) => k !== "/" && pathname.startsWith(k));
  return match ? PAGE_META[match] : { kicker: "SIPRO", title: "Beranda" };
}

export default function TopBar({ onMenuClick }) {
  const location = useLocation();
  const navigate = useNavigate();
  const navigateRef = useRef(navigate);
  useEffect(() => { navigateRef.current = navigate; }, [navigate]);
  const { user, logout, switchOrg } = useAuth();
  const [unread, setUnread] = useState(0);
  const [orgs, setOrgs] = useState([]);
  const isSuper = user?.role === "super_admin";
  const activeOrgName = user?.active_org?.name;
  const esRef = useRef(null);
  const wsRef = useRef(null);
  const meta = resolveMeta(location.pathname);

  const loadUnread = useCallback(async () => {
    try {
      const res = await api.get("/notifications", { params: { unread_only: true, limit: 1 } });
      setUnread(res.data.unread || 0);
    } catch { /* ignore */ }
  }, []);

  // Polling fallback (30s) + refresh on route change (kept as safety net).
  useEffect(() => {
    loadUnread();
    const t = setInterval(loadUnread, 30000);
    return () => clearInterval(t);
  }, [loadUnread, location.pathname]);

  // Super_admin: load tenant list for the org-switcher.
  useEffect(() => {
    if (!isSuper) return;
    api.get("/admin/orgs").then((r) => setOrgs(r.data.data || [])).catch(() => { /* ignore */ });
  }, [isSuper]);

  const handleSwitch = async (orgId) => {
    if (orgId === user?.org_id) return;
    try { await switchOrg(orgId); } catch { toast.error("Gagal beralih organisasi."); }
  };

  // Real-time notifications via WebSocket (EPIC M3) — event-driven instant push
  // (a notification arrives the moment it is created, no ~2s poll) with a 25s
  // heartbeat + auto-reconnect. Falls back to SSE (EventSource) automatically if
  // the WebSocket cannot be established (proxy without upgrade, etc.).
  useEffect(() => {
    if (!user) return undefined;
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) return undefined;

    let ws = null;
    let pingTimer = null;
    let reconnectTimer = null;
    let closed = false;
    let attempts = 0;

    const setCount = (d) => {
      if (d && typeof d.unread === "number") setUnread(d.unread);
    };
    const onNotification = (n) => {
      toast(n.title || "Notifikasi baru", {
        description: n.body || undefined,
        action: { label: "Lihat", onClick: () => navigateRef.current("/notifications") },
      });
    };

    // ---- SSE fallback (only used if WebSocket keeps failing) ----
    const startSSE = () => {
      if (closed || esRef.current) return;
      let es;
      try {
        es = new EventSource(`${API}/notifications/stream?token=${encodeURIComponent(token)}`);
      } catch {
        return;
      }
      esRef.current = es;
      const onCount = (e) => { try { setCount(JSON.parse(e.data)); } catch { /* ignore */ } };
      es.addEventListener("hello", onCount);
      es.addEventListener("ping", onCount);
      es.addEventListener("notification", (e) => {
        try { setUnread((u) => u + 1); onNotification(JSON.parse(e.data)); } catch { /* ignore */ }
      });
      es.onerror = () => { /* browser auto-reconnects; polling covers gaps */ };
    };

    // ---- WebSocket (primary) ----
    const connectWS = () => {
      if (closed) return;
      const wsBase = API.replace(/^http/i, "ws"); // https->wss, http->ws
      let socket;
      try {
        socket = new WebSocket(`${wsBase}/ws/notifications?token=${encodeURIComponent(token)}`);
      } catch {
        startSSE();
        return;
      }
      ws = socket;
      wsRef.current = socket;

      socket.onopen = () => {
        attempts = 0;
        pingTimer = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ action: "ping" }));
          }
        }, 25000);
      };
      socket.onmessage = (e) => {
        let msg;
        try { msg = JSON.parse(e.data); } catch { return; }
        if (msg.event === "notification" && msg.data) {
          if (typeof msg.unread === "number") setUnread(msg.unread); else setUnread((u) => u + 1);
          onNotification(msg.data);
        } else if (msg.event === "hello" || msg.event === "unread") {
          setCount(msg);
        }
      };
      socket.onclose = (ev) => {
        if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
        wsRef.current = null;
        if (closed) return;
        if (ev.code === 4401) return; // auth rejected — do not hammer reconnect
        attempts += 1;
        if (attempts >= 3) { startSSE(); return; } // give up on WS -> SSE fallback
        reconnectTimer = setTimeout(connectWS, Math.min(1000 * attempts, 5000));
      };
      socket.onerror = () => { try { socket.close(); } catch { /* noop */ } };
    };

    // StrictMode's setup-cleanup-setup must not open then abort a CONNECTING socket.
    const startTimer = setTimeout(connectWS, 0);

    return () => {
      closed = true;
      clearTimeout(startTimer);
      if (pingTimer) clearInterval(pingTimer);
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) {
        ws.onmessage = null;
        if (ws.readyState === WebSocket.CONNECTING) ws.onopen = () => ws.close();
        else { try { ws.close(); } catch { /* noop */ } }
      }
      if (esRef.current) { try { esRef.current.close(); } catch { /* noop */ } }
      wsRef.current = null;
      esRef.current = null;
    };
  }, [user?.email, user?.org_id]);

  const doLogout = async () => {
    if (wsRef.current) { try { wsRef.current.close(); } catch { /* noop */ } }
    if (esRef.current) { try { esRef.current.close(); } catch { /* noop */ } }
    await logout();
    navigate("/login");
  };

  return (
    <header data-testid={NAV.topbar} className="sticky top-0 z-20 flex items-center justify-between border-b border-border bg-card/85 px-4 py-3 shadow-[var(--shadow-card)] backdrop-blur-md md:px-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" className="md:hidden" onClick={onMenuClick}>
          <Menu className="h-5 w-5" />
        </Button>
        <div>
          <p className="eyebrow">{meta.kicker}</p>
          <h1 data-testid={NAV.pageTitle} className="font-heading text-lg font-semibold leading-tight tracking-tight">{meta.title}</h1>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {user?.demo_data ? (
          <span data-testid={NAV.demoBadge}
            title="Akun dan transaksi di lingkungan ini adalah data demo/uji, bukan data produksi."
            className="inline-flex items-center gap-1.5 rounded-full border border-amber-300/70 bg-amber-50 px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-amber-800 sm:px-2.5 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-200">
            <FlaskConical className="h-3.5 w-3.5 shrink-0" /> <span className="hidden sm:inline">Data demo</span>
          </span>
        ) : null}
        {isSuper ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button data-testid={NAV.orgSwitcher}
                className={`hidden items-center gap-2 rounded-lg border px-2.5 py-1.5 text-sm transition-colors hover:bg-secondary sm:flex ${user?.is_switched ? "border-primary/40 bg-primary/5" : ""}`}
                title="Beralih organisasi">
                <Building2 className="h-4 w-4 text-primary" />
                <span className="max-w-[160px] truncate font-medium">{activeOrgName || "Organisasi"}</span>
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuLabel>Beralih Organisasi</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {orgs.map((o) => (
                <DropdownMenuItem key={o.id} data-testid={NAV.orgSwitcherItem}
                  onClick={() => handleSwitch(o.id)} className="flex items-center justify-between gap-2">
                  <span className="truncate">{o.name}</span>
                  {o.id === user?.org_id ? <Check className="h-4 w-4 text-primary" /> : null}
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => navigate("/admin/organizations")}>
                <Building2 className="mr-2 h-4 w-4" /> Kelola Organisasi
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
        <BellSummary unread={unread} onUnread={setUnread} />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button data-testid={NAV.profileMenu} className="flex items-center gap-2 rounded-lg py-1 pl-1 pr-2 hover:bg-secondary transition-colors">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-semibold">
                {initials(user?.name)}
              </span>
              <span className="hidden text-left sm:block">
                <span className="block text-sm font-medium leading-none">{user?.name}</span>
                <span className="block text-[11px] text-muted-foreground">{user?.role_label || roleLabel(user?.role)}</span>
              </span>
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>
              <p className="font-medium">{user?.name}</p>
              <p className="text-xs font-normal text-muted-foreground">{user?.email}</p>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem data-testid={PROFILE.menuItem} onClick={() => navigate("/profile")}>
              <UserCircle2 className="h-4 w-4 mr-2" /> Profil Saya
            </DropdownMenuItem>
            <DropdownMenuItem data-testid={AUTH.logoutButton} onClick={doLogout} className="text-rose-600 focus:text-rose-600">
              <LogOut className="h-4 w-4 mr-2" /> Keluar
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
