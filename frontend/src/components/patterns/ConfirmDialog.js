import React from "react";
import { AlertTriangle } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

/**
 * ConfirmDialog — konfirmasi eksplisit untuk aksi merusak (hapus / arsip).
 *
 * Sebelum ini beberapa aksi hapus (unit, fase, skema, arsip template) langsung
 * dieksekusi begitu ikon diklik — sekali salah klik, data master hilang tanpa
 * peringatan. Semua aksi merusak sekarang melewati dialog ini.
 */
export default function ConfirmDialog({
  open, onOpenChange, title = "Konfirmasi", description,
  confirmLabel = "Hapus", cancelLabel = "Batal",
  destructive = true, busy = false, onConfirm, testId = "confirm-dialog",
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={testId} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {destructive ? <AlertTriangle className="h-4 w-4 text-rose-600" /> : null}
            {title}
          </DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        <DialogFooter>
          <Button data-testid="confirm-cancel" variant="outline" disabled={busy}
            onClick={() => onOpenChange(false)}>
            {cancelLabel}
          </Button>
          <Button data-testid="confirm-accept" disabled={busy}
            variant={destructive ? "destructive" : "default"}
            onClick={onConfirm}>
            {busy ? "Memproses\u2026" : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
