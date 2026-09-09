import React from "react";
import { NavLink } from "react-router-dom";
import { Building2, Lock, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { buildNavGroups } from "@/config/navigationConfig";
import NavMigrationDialog from "@/components/layout/NavMigrationDialog";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";
import { NAV, HUB } from "@/constants/testIds";

function NavItem({ item, collapsed }) {
  const Icon = item.icon;
  if (item.comingSoon) {
    return (
      <div
        data-testid={`${NAV.navItemPrefix}-${item.id}`}
        data-coming-soon="true"
        aria-disabled="true"
        className={cn(
          "flex items-center rounded-lg px-3 py-2 text-sm text-muted-foreground/70 cursor-not-allowed",
          collapsed ? "justify-center px-0" : "justify-between",
        )}
        title={item.note ? `${item.label} — segera hadir (${item.note})`
          : `${item.label} — segera hadir`}
      >
        <span className={cn("flex items-center gap-2.5", collapsed && "gap-0")}>
          {Icon ? <Icon className="h-4 w-4" /> : null}
          {collapsed ? null : item.label}
        </span>
        {collapsed ? null : <Lock data-testid={HUB.navSoon} className="h-3 w-3" />}
      </div>
    );
  }
  return (
    <NavLink
      to={item.path}
      end={item.path === "/"}
      data-testid={`${NAV.navItemPrefix}-${item.id}`}
      title={collapsed ? item.label : undefined}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card",
          collapsed && "justify-center gap-0 px-0",
          // Fase 67: menu aktif ditandai blok aksen + garis kiri (bukan hanya warna teks),
          // dan menu tidak aktif punya hover yang terasa (dulu nyaris tidak berubah).
          isActive
            ? "bg-primary text-primary-foreground shadow-sm ring-1 ring-primary/20"
            : "text-foreground/75 hover:bg-secondary hover:text-foreground",
        )
      }
    >
      {Icon ? <Icon className="h-4 w-4 shrink-0" />
        : (collapsed ? <span className="text-xs font-semibold">{(item.label || "?")[0]}</span> : null)}
      {collapsed ? null : item.label}
    </NavLink>
  );
}

export default function Sidebar({ role, onNavigate, collapsed = false, onToggle }) {
  // Menu disaring dengan izin EFEKTIF (bukan hanya peran): pencabutan akses di layar
  // Hak Akses langsung menyembunyikan pintunya. Saat izin belum termuat (bootstrap),
  // saringan izin dilewati agar sidebar tidak berkedip kosong.
  const { can, permsKnown } = useAuth();
  const groups = buildNavGroups(role, permsKnown ? can : null);
  return (
    <aside
      data-testid={NAV.sidebar}
      data-collapsed={collapsed ? "true" : "false"}
      className={cn(
        "flex h-full shrink-0 flex-col border-r border-border bg-card shadow-[var(--shadow-card)] transition-[width] duration-200",
        collapsed ? "w-16" : "w-64",
      )}
      onClick={onNavigate}
    >
      <div className={cn(
        "flex items-center border-b border-border bg-[hsl(var(--surface-sunken))]",
        collapsed ? "flex-col gap-2 px-2 py-3" : "gap-2.5 px-4 py-4",
      )}>
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
          <Building2 className="h-5 w-5" />
        </div>
        {collapsed ? null : (
          <div className="min-w-0 flex-1">
            <p className="font-heading font-bold leading-none tracking-tight">SIPRO</p>
            <p className="text-[10px] text-muted-foreground mt-0.5">Property Development OS</p>
          </div>
        )}
        {onToggle ? (
          <button
            type="button"
            data-testid="sidebar-collapse-toggle"
            aria-label={collapsed ? "Perlebar menu samping" : "Ciutkan menu samping"}
            title={collapsed ? "Perlebar menu" : "Ciutkan menu"}
            onClick={(e) => { e.stopPropagation(); onToggle(); }}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
        ) : null}
      </div>
      <nav className={cn("flex-1 overflow-y-auto py-4", collapsed ? "px-2 space-y-3" : "px-3 space-y-5")}>
        {groups.map((group) => {
          if (group.type === "standalone") {
            return <NavItem key={group.id} item={group} collapsed={collapsed} />;
          }
          return (
            <div key={group.groupId}>
              {collapsed ? (
                <div className="mx-2 mb-1.5 border-t border-border/70" aria-hidden="true" />
              ) : (
                <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground/80">
                  {group.label}
                </p>
              )}
              <div className="space-y-0.5">
                {group.items.map((it) => <NavItem key={it.id} item={it} collapsed={collapsed} />)}
              </div>
            </div>
          );
        })}
      </nav>
      {/* Fase 40c: pintu ke PETA MENU (lama→baru). Diletakkan di dasar sidebar karena di
          situlah pemakai mencari bantuan setelah gagal menemukan menu yang ia hafal. */}
      {collapsed ? null : (
        <div className="border-t px-4 py-2.5" onClick={(e) => e.stopPropagation()}>
          <NavMigrationDialog />
          <p className="mt-1 text-[10px] text-muted-foreground">
            SIPRO · Property Development OS · v1.0
          </p>
        </div>
      )}
    </aside>
  );
}
