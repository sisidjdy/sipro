import React from "react";
import { cn } from "@/lib/utils";
import { useReference } from "@/context/ReferenceContext";

/**
 * Label fallback lokal. SUMBER UTAMA label enum adalah registry backend
 * (`GET /api/reference`) yang diakses lewat prop `group`; peta di bawah hanya
 * dipakai bila komponen dirender di luar konteks referensi (mis. portal pembeli
 * yang tidak memakai sesi staf) atau bila `group` tidak diberikan.
 */
const LABELS = {
  open: "Terbuka", in_progress: "Dikerjakan", completed: "Selesai", snoozed: "Ditunda",
  urgent: "Urgent", high: "Tinggi", medium: "Sedang", low: "Rendah",
  available: "Tersedia", holding: "Holding", reserved: "Reserved", booked: "Booked",
  sold: "Terjual", overdue: "Terlambat", "due-today": "Hari ini", "on-track": "On-track",
  simulation: "SIMULASI",
  acquisition: "Akuisisi", nurturing: "Nurturing", appointment: "Appointment", booking: "Booking",
  won: "Menang", recycle: "Daur Ulang", lost: "Hilang",
  hot: "Hot", warm: "Warm", cold: "Cold",
  draft: "Draft", finalized: "Final", signed: "Ditandatangani",
  expired: "Kadaluarsa", cancelled: "Batal", active: "Aktif", closed: "Selesai", new: "Baru",
  unpaid: "Belum Bayar", partial: "Sebagian", paid: "Lunas", pending: "Menunggu",
  pending_approval: "Menunggu Approval", approved: "Disetujui", paid_off: "Lunas",
  booking_fee: "Booking Fee",
  scheduled: "Terjadwal", done: "Selesai", no_show: "Tidak Hadir",
  recommended: "Direkomendasikan", needs_followup: "Perlu Tindak Lanjut",
  not_recommended: "Tidak Direkomendasikan",
  reported: "Dilaporkan", issued: "Terbit",
  submitted: "Diajukan", verified: "Ter-opname", rejected: "Ditolak",
  passed: "Lulus", failed: "Gagal", na: "N/A",
  // Status fase konstruksi (dulu tidak ada -> pill menampilkan "not_started"/"qc_hold" mentah)
  not_started: "Belum mulai", qc_hold: "QC hold",
  planning: "Perencanaan", on_hold: "Ditahan", archived: "Diarsipkan", resolved: "Selesai",
};

/**
 * StatusPill — badge status.
 *
 * @param status  nilai enum mentah (mis. "not_started"); dipakai untuk mencari label
 * @param group   nama grup reference (mis. "construction_status") -> label dari SSOT backend
 * @param label   paksa teks tertentu (hindari mengirim nilai enum mentah ke sini!)
 * @param tone    kunci gaya warna bila berbeda dari `status`
 */
export default function StatusPill({ status, label, group, tone, className }) {
  const { labelOf } = useReference();
  const key = String(status || "").toLowerCase();
  const toneKey = String(tone || status || "").toLowerCase();
  const fromRef = group ? labelOf(group, status) : null;
  const text = label
    || (fromRef && fromRef !== status && fromRef !== "-" ? fromRef : null)
    || LABELS[key]
    || status;
  return (
    <span data-testid="status-pill" data-status={key}
      className={cn("status-pill", `status-${toneKey}`, className)}>
      {text}
    </span>
  );
}
