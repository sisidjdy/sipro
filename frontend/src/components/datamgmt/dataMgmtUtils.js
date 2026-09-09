import { toast } from "sonner";
import api from "@/services/apiClient";

/** Unduh berkas biner dari API (nama berkas diambil dari header Content-Disposition). */
export async function downloadFile(url, fallbackName, params) {
  try {
    const res = await api.get(url, { responseType: "blob", params });
    const cd = res.headers?.["content-disposition"] || "";
    const m = /filename\*=UTF-8''([^;]+)/i.exec(cd) || /filename="?([^";]+)"?/i.exec(cd);
    const name = m ? decodeURIComponent(m[1]) : fallbackName;
    const href = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = href; a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(href), 30000);
    return true;
  } catch (e) {
    let detail = "Gagal mengunduh berkas.";
    try { detail = JSON.parse(await e?.response?.data?.text())?.detail || detail; } catch { /* blob */ }
    toast.error(detail);
    return false;
  }
}

export function formatBytes(n) {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB"];
  const i = Math.min(u.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`;
}

export const errDetail = (e, fallback) => e?.response?.data?.detail || fallback;
