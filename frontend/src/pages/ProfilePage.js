import React from "react";
import { UserCircle2 } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { roleLabel, initials } from "@/utils/formatters";
import { ProfileForm, PasswordForm } from "@/components/profile/ProfileForms";
import { MyPermissions, MyActivity } from "@/components/profile/ProfilePanels";
import { PROFILE } from "@/constants/testIds";

/** Profil saya — data diri, kata sandi, hak akses efektif, dan jejak aktivitas sendiri. */
export default function ProfilePage() {
  const { user } = useAuth();
  return (
    <div data-testid={PROFILE.page} className="space-y-5">
      <div className="flex items-center gap-2">
        <UserCircle2 className="h-5 w-5 text-primary" />
        <div><h1 className="page-title">Profil Saya</h1>
          <p className="page-desc">Perbarui data diri dan kata sandi Anda; lihat izin yang berlaku untuk akun ini.</p></div>
      </div>
      <div className="flex flex-wrap items-center gap-4 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
        <span data-testid={PROFILE.avatar} className="flex h-14 w-14 items-center justify-center rounded-full bg-primary text-lg font-semibold text-primary-foreground">
          {initials(user?.name)}
        </span>
        <div className="min-w-0">
          <p data-testid={PROFILE.name} className="font-heading text-lg font-semibold leading-tight">{user?.name}</p>
          <p data-testid={PROFILE.email} className="font-mono text-xs text-muted-foreground">{user?.email}</p>
          <p className="mt-1 flex flex-wrap gap-1.5 text-[11px]">
            <span data-testid={PROFILE.role} className="rounded-full border bg-accent/50 px-2 py-0.5">{user?.role_label || roleLabel(user?.role)}</span>
            {user?.active_org?.name ? <span data-testid={PROFILE.org} className="rounded-full border px-2 py-0.5 text-muted-foreground">{user.active_org.name}</span> : null}
            {user?.phone ? <span className="rounded-full border px-2 py-0.5 text-muted-foreground">{user.phone}</span> : null}
          </p>
        </div>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <ProfileForm key={`${user?.name}|${user?.phone}`} />
        <PasswordForm />
        <MyPermissions />
        <MyActivity />
      </div>
    </div>
  );
}
