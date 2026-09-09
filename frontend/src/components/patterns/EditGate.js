import React from "react";
import { Lock } from "lucide-react";

import { useAuth } from "@/context/AuthContext";

/**
 * EditGate — RBAC di sisi tampilan untuk panel master/konfigurasi.
 * Bila peran tidak punya izin `resource:action`, semua kontrol di dalamnya dimatikan
 * (fieldset disabled) dan tampil spanduk "hanya baca" — bukan tombol yang selalu ditolak 403.
 */
export default function EditGate({ resource, action = "update", children, testId }) {
  const { can } = useAuth();
  const allowed = can(resource, action);
  if (allowed) return children;
  return (
    <div data-testid={testId || `edit-gate-${resource}`} data-readonly="true" className="space-y-3">
      <p className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
        <Lock className="h-3.5 w-3.5" />
        Mode hanya baca — peran Anda tidak memiliki izin <code>{resource}:{action}</code>. Hubungi admin untuk mengubah data ini.
      </p>
      <fieldset disabled className="min-w-0 opacity-80 [&_button]:pointer-events-none [&_input]:pointer-events-none">
        {children}
      </fieldset>
    </div>
  );
}
