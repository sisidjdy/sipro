import React, { useEffect, useState } from "react";
import { Eye, Lock, LayoutList } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { buildNavGroups } from "@/config/navigationConfig";
import api from "@/services/apiClient";
import { ADMIN } from "@/constants/testIds";

/** `can()` untuk SEBUAH peran dari izin efektif server (logika sama dengan AuthContext.can). */
export const canFor = (role, perms) => (resource, action) => {
  if (!perms) return false;
  if (perms.fullAccess.includes(role)) return true;
  const list = perms.effective?.[resource]?.[role]?.perms || [];
  if (list.includes("manage") || list.includes("all") || list.includes(action)) return true;
  return action === "view" && ["view", "view_all", "view_own"].some((a) => list.includes(a));
};

export const navRoleOf = (role, perms) => {
  const m = perms?.roleMeta?.[role];
  return m?.custom ? (m.inherits || role) : role;
};

export const menusFor = (role, perms) => {
  if (!role || !perms) return [];
  return buildNavGroups(navRoleOf(role, perms), canFor(role, perms));
};

/** Ambil izin efektif + meta peran sekali; dipakai pratinjau menu di beberapa layar. */
export function useRolePerms(enabled = true) {
  const [perms, setPerms] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    api.get("/admin/permissions").then((r) => {
      if (!alive) return;
      const d = r.data.data;
      setPerms({ effective: d.effective || {}, roleMeta: d.role_meta || {}, fullAccess: d.full_access_roles || [] });
    }).catch((e) => alive && setError(e?.response?.data?.detail || "Izin peran tidak bisa dimuat."));
    return () => { alive = false; };
  }, [enabled]);
  return { perms, error };
}

/** Daftar menu (grup → item) yang akan tampil di sidebar untuk `role`. */
export function RoleMenuList({ role, perms, compact = false }) {
  const groups = menusFor(role, perms);
  const total = groups.reduce((n, g) => n + (g.type === "standalone" ? 1 : g.items.length), 0);
  if (!role) return <p className="text-xs text-muted-foreground">Pilih peran untuk melihat menunya.</p>;
  if (!perms) return <p className="text-xs text-muted-foreground">Memuat izin…</p>;
  return (
    <div data-testid={ADMIN.rolePreviewList} data-role={role} className="space-y-2">
      <p data-testid={ADMIN.rolePreviewCount} className="text-xs text-muted-foreground">
        <b>{total}</b> menu akan tampil di sidebar{perms.roleMeta?.[role]?.custom && perms.roleMeta[role].inherits
          ? <> · struktur menu mengikuti peran induk <b>{perms.roleMeta[perms.roleMeta[role].inherits]?.label || perms.roleMeta[role].inherits}</b></> : null}.
      </p>
      {!groups.length ? (
        <p data-testid={ADMIN.rolePreviewEmpty} className="rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground">
          Belum ada menu: peran ini belum punya izin lihat pada resource mana pun. Centang izinnya di matriks.
        </p>
      ) : null}
      <div className={compact ? "grid gap-2 sm:grid-cols-2" : "grid gap-3 sm:grid-cols-2 lg:grid-cols-3"}>
        {groups.map((g) => (
          <div key={g.groupId || g.id} data-testid={ADMIN.rolePreviewGroup} data-group={g.groupId || g.id} className="rounded-md border bg-card px-3 py-2">
            <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">{g.label}</p>
            <ul className="mt-1 space-y-0.5 text-xs">
              {(g.type === "standalone" ? [g] : g.items).map((it) => (
                <li key={it.id} data-testid={ADMIN.rolePreviewItem} data-item={it.id} className="flex items-center gap-1.5">
                  {it.icon ? <it.icon className="h-3 w-3 text-muted-foreground" /> : null}
                  <span className={it.comingSoon ? "text-muted-foreground" : ""}>{it.label}</span>
                  {it.comingSoon ? <span className="inline-flex items-center gap-0.5 rounded border px-1 text-[9px] text-muted-foreground"><Lock className="h-2.5 w-2.5" /> terkunci</span> : null}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Dialog pratinjau menu satu peran (dibuka dari Daftar Peran & form pengguna). */
export function RoleMenuPreviewDialog({ role, label, onClose }) {
  const { perms, error } = useRolePerms(true);
  const title = label || perms?.roleMeta?.[role]?.label || role;
  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent data-testid={ADMIN.rolePreviewDialog} className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><LayoutList className="h-4 w-4 text-primary" /> Pratinjau menu: {title}</DialogTitle>
          <DialogDescription>
            Menu yang akan dilihat pengguna berperan ini setelah login — dihitung dari izin efektif saat ini (matriks, warisan, tambahan kode).
          </DialogDescription>
        </DialogHeader>
        {error ? <p data-testid={ADMIN.rolePreviewError} className="text-sm text-destructive">{error}</p> : <RoleMenuList role={role} perms={perms} />}
      </DialogContent>
    </Dialog>
  );
}

/** Tombol ikon "lihat menu" yang membuka dialog pratinjau untuk `role`. */
export function RolePreviewButton({ role, label, testId, className = "" }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button type="button" variant="outline" size="icon" className={`h-9 w-9 shrink-0 ${className}`} data-testid={testId} data-role={role || ""}
        disabled={!role} aria-label="Pratinjau menu peran" title="Lihat menu yang akan dilihat peran ini" onClick={() => setOpen(true)}>
        <Eye className="h-4 w-4" />
      </Button>
      {open ? <RoleMenuPreviewDialog role={role} label={label} onClose={() => setOpen(false)} /> : null}
    </>
  );
}
