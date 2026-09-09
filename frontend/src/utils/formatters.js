// Formatters — IDR (integer), tanggal WIB (Asia/Jakarta), waktu relatif ID.

export const formatIDR = (value) =>
  new Intl.NumberFormat("id-ID", {
    style: "currency", currency: "IDR", maximumFractionDigits: 0,
  }).format(Number(value) || 0);

export const formatNumber = (value) =>
  new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 }).format(Number(value) || 0);

// Bentuk ringkas untuk ruang sempit (sumbu grafik, bilah mini): 2.300.000.000 → "2,3 M".
export const formatCompact = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  const abs = Math.abs(n);
  const short = (div, suffix) => `${formatNumber(Math.round((n / div) * 10) / 10)} ${suffix}`;
  if (abs >= 1e12) return short(1e12, "T");
  if (abs >= 1e9) return short(1e9, "M");
  if (abs >= 1e6) return short(1e6, "jt");
  if (abs >= 1e4) return short(1e3, "rb");
  return formatNumber(n);
};

export const formatDateWIB = (iso) => {
  if (!iso) return "-";
  try {
    return new Intl.DateTimeFormat("id-ID", {
      day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Jakarta",
    }).format(new Date(iso));
  } catch { return "-"; }
};

export const formatDateTimeWIB = (iso) => {
  if (!iso) return "-";
  try {
    return new Intl.DateTimeFormat("id-ID", {
      day: "numeric", month: "short", year: "numeric", hour: "2-digit",
      minute: "2-digit", timeZone: "Asia/Jakarta",
    }).format(new Date(iso)) + " WIB";
  } catch { return "-"; }
};

export const fromNow = (iso) => {
  if (!iso) return "";
  const diffMs = new Date(iso).getTime() - Date.now();
  const past = diffMs < 0;
  const mins = Math.round(Math.abs(diffMs) / 60000);
  let label;
  if (mins < 1) label = "beberapa detik";
  else if (mins < 60) label = `${mins} menit`;
  else if (mins < 1440) label = `${Math.round(mins / 60)} jam`;
  else label = `${Math.round(mins / 1440)} hari`;
  return past ? `${label} lalu` : `dalam ${label}`;
};

// SLA / due label for TaskCard.
export const dueLabel = (iso) => {
  if (!iso) return { text: "Tanpa tenggat", tone: "muted" };
  const diffMs = new Date(iso).getTime() - Date.now();
  if (diffMs < 0) {
    return { text: `Terlambat ${fromNow(iso).replace(" lalu", "")}`, tone: "overdue" };
  }
  const hours = diffMs / 3600000;
  if (hours < 24) return { text: `Jatuh tempo ${fromNow(iso)}`, tone: "due-today" };
  return { text: `Jatuh tempo ${fromNow(iso)}`, tone: "on-track" };
};

export const initials = (name = "") =>
  name.split(" ").filter(Boolean).slice(0, 2).map((s) => s[0]?.toUpperCase()).join("") || "?";

export const roleLabel = (role) => ({
  super_admin: "Super Admin", owner: "Owner", sales_manager: "Manajer Sales",
  marketing_admin: "Admin Marketing", sales: "Sales", finance: "Finance",
  project_manager: "Manajer Proyek", site_engineer: "Site Engineer",
  dm_supervisor: "Supervisor Digital Marketing", dm_staff: "Staf Digital Marketing",
  finance_manager: "Supervisor Keuangan", legal_admin: "Admin Legal & Kepatuhan",
}[role] || role || "-");
