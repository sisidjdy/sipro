import React from "react";
import { AlertTriangle, CalendarClock, CalendarDays, PauseCircle, CheckCheck,
  Hourglass } from "lucide-react";
import TaskCard from "@/components/patterns/TaskCard";
import EmptyState from "@/components/patterns/EmptyState";
import { HOME } from "@/constants/testIds";

const SECTIONS = [
  { key: "overdue", label: "Terlambat", icon: AlertTriangle, tone: "text-rose-600" },
  { key: "today", label: "Hari Ini", icon: CalendarClock, tone: "text-amber-600" },
  { key: "review", label: "Menunggu Verifikasi", icon: Hourglass, tone: "text-sky-600" },
  { key: "upcoming", label: "Akan Datang", icon: CalendarDays, tone: "text-sky-600" },
  { key: "waiting", label: "Ditunda", icon: PauseCircle, tone: "text-muted-foreground" },
];

export default function TaskInbox({ buckets, onComplete, onSnooze, onOpen }) {
  const total = SECTIONS.reduce((n, s) => n + (buckets?.[s.key]?.length || 0), 0);
  if (!total) {
    return (
      <EmptyState
        icon={CheckCheck}
        title="Tidak ada tugas aktif"
        description="Kerja bagus! Tugas baru muncul otomatis dari jobdesk divisi Anda — dari lead masuk, temuan lapangan, tenggat pembayaran, sampai tugas berulang harian."
      />
    );
  }
  return (
    <div data-testid={HOME.taskInbox} className="space-y-5">
      {SECTIONS.map((s) => {
        const items = buckets?.[s.key] || [];
        if (!items.length) return null;
        const Icon = s.icon;
        return (
          <div key={s.key}>
            <div className="mb-2 flex items-center gap-2">
              <Icon className={`h-4 w-4 ${s.tone}`} />
              <h3 className="text-sm font-semibold">{s.label}</h3>
              <span className="rounded-full bg-secondary px-2 text-xs text-muted-foreground tabular-nums">
                {items.length}
              </span>
            </div>
            <div className="grid gap-2.5">
              {items.map((t) => (
                <TaskCard key={t.id} task={t} onComplete={onComplete} onSnooze={onSnooze}
                  onOpen={onOpen} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
