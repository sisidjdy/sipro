import React from "react";
import { ShieldOff } from "lucide-react";

import TimelineFeed from "@/components/patterns/TimelineFeed";
import { PANELSTATE } from "@/constants/testIds";

/**
 * LeadTimelineTab — satu urutan waktu dari SEMUA jejak lead: perpindahan tahap, aktivitas/
 * catatan, appointment, dan penyerahan dokumen. Setiap baris menyebut aktornya (CR-10).
 *
 * Fase 52 — tab ini MENGGABUNG beberapa sumber, jadi ia paling mudah berbohong: bila satu
 * sumber ditolak izin (mis. jadwal survei) urutan waktunya tetap tampil "lengkap" padahal
 * ada bagian yang sengaja tidak disertakan. Karena itu `omitted` (dari `omittedSources()`)
 * ditulis apa adanya di atas daftar: pemakai tahu jejak ini SEBAGIAN, dan tahu sebabnya.
 */
function build({ lead, activities, appointments, submissions }) {
  const items = [];
  (lead?.stage_history || []).forEach((h) => items.push({
    at: h.at, actor: h.actor, kind: "stage",
    title: `Tahap ${h.from || "-"} → ${h.to}${h.override ? " (override supervisor)" : ""}`,
    body: h.reason || null,
  }));
  (activities || []).forEach((a) => items.push({
    at: a.created_at, actor: a.actor || a.created_by, kind: a.type === "comment"
      ? "activity" : "activity",
    title: a.type === "comment" ? "Catatan" : (a.title || "Aktivitas"),
    body: a.body,
  }));
  (appointments || []).forEach((ap) => items.push({
    at: ap.created_at || ap.scheduled_at, actor: ap.created_by || ap.assigned_to,
    kind: "task", title: `Appointment: ${ap.title}`,
    body: `${ap.location || "-"} · status ${ap.status}`,
  }));
  (submissions || []).forEach((s) => items.push({
    at: s.submitted_at || s.created_at, actor: s.submitted_by, kind: "upload",
    title: `Dokumen “${s.requirement_label || s.requirement_code}” diserahkan`,
    body: s.status === "verified"
      ? `Diverifikasi oleh ${s.verified_by || "-"}`
      : s.status === "rejected" ? `Ditolak: ${s.reject_reason || "-"}` : "Menunggu verifikasi",
  }));
  return items;
}

export default function LeadTimelineTab(props) {
  const omitted = (props.omitted || []).filter((o) => o.key !== "lifecycle");
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Seluruh jejak lead ini dalam satu urutan waktu — termasuk siapa yang mengerjakan.
      </p>
      {omitted.length ? (
        <div data-testid={PANELSTATE.omitted}
          className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
          <p className="flex items-center gap-2 font-medium text-slate-900">
            <ShieldOff className="h-4 w-4" /> Jejak ini SEBAGIAN
          </p>
          <ul className="mt-1 space-y-0.5 text-xs">
            {omitted.map((o) => (
              <li key={o.key}>• {o.label} tidak disertakan — {o.reason}.</li>
            ))}
          </ul>
        </div>
      ) : null}
      <TimelineFeed items={build(props)}
        emptyText={omitted.length
          ? "Tidak ada jejak yang bisa ditampilkan dari sumber yang boleh Anda baca."
          : "Belum ada jejak untuk lead ini (belum ada perpindahan tahap, catatan, atau dokumen)."} />
    </div>
  );
}
