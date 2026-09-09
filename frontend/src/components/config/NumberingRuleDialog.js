import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import api from "@/services/apiClient";
import { NUMBERING } from "@/constants/testIds";

const pick = (r) => ({
  pattern: r.pattern || "", prefix: r.prefix ?? "", width: r.width || 4,
  reset: r.reset || "yearly", seq_scope: r.seq_scope || "tokens", start: r.start || 1,
});

/** Dialog ubah satu aturan penomoran — pratinjau hidup dari server (counter tidak naik). */
export default function NumberingRuleDialog({ rule, canEdit, resetOptions, scopeOptions, projectId, onClose, onSaved }) {
  const [form, setForm] = useState(pick(rule));
  const [tokens, setTokens] = useState([]);
  const [preview, setPreview] = useState(rule.preview || "");
  const [previewError, setPreviewError] = useState("");
  const [saving, setSaving] = useState(false);
  const patternRef = useRef(null);

  useEffect(() => {
    api.get(`/numbering/${rule.key}/tokens`).then((r) => setTokens(r.data.data || [])).catch(() => {});
  }, [rule.key]);

  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const res = await api.post(`/numbering/${rule.key}/preview`, {
          ...form, width: Number(form.width) || undefined, start: Number(form.start) || undefined,
          project_id: projectId || undefined,
        });
        setPreview(res.data.data.preview); setPreviewError("");
      } catch (e) {
        setPreviewError(e?.response?.data?.detail || "Pola tidak sah.");
      }
    }, 250);
    return () => clearTimeout(t);
  }, [form, rule.key, projectId]);

  const insertToken = (tok) => {
    const el = patternRef.current;
    const pos = el?.selectionStart ?? form.pattern.length;
    const next = `${form.pattern.slice(0, pos)}{${tok}}${form.pattern.slice(pos)}`;
    setForm({ ...form, pattern: next });
    setTimeout(() => el?.focus(), 0);
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/numbering/${rule.key}`, {
        ...form, width: Number(form.width), start: Number(form.start),
      });
      toast.success("Aturan penomoran disimpan.");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan aturan.");
    } finally { setSaving(false); }
  };

  const resetDefault = async () => {
    try {
      await api.delete(`/numbering/${rule.key}`);
      toast.success("Aturan dikembalikan ke bawaan.");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengembalikan aturan.");
    }
  };

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent data-testid={NUMBERING.dialog} className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Penomoran — {rule.label}</DialogTitle>
          <DialogDescription>
            Bawaan: <code>{rule.default?.pattern}</code>. Klik token untuk menyisipkannya ke pola.
            Token konteks (proyek, vendor, …) memisahkan urutan bila cakupan = per token.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="nb-pattern">Pola</Label>
            <Input id="nb-pattern" ref={patternRef} data-testid={NUMBERING.formPattern}
              value={form.pattern} disabled={!canEdit} className="font-mono"
              placeholder="{PREFIX}/{YYYY}/{SEQ}"
              onChange={(e) => setForm({ ...form, pattern: e.target.value })} />
            <div className="flex flex-wrap gap-1">
              {tokens.map((t) => (
                <button key={t.token} type="button" data-testid={NUMBERING.tokenChip}
                  title={`${t.desc} — contoh: ${t.example}`} disabled={!canEdit}
                  onClick={() => insertToken(t.token)}
                  className={`rounded border px-1.5 py-0.5 font-mono text-[11px] transition-colors hover:bg-accent ${
                    t.kind === "konteks" ? "border-sky-200 bg-sky-50 text-sky-900" : "bg-muted"}`}>
                  {`{${t.token}}`}
                </button>
              ))}
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="space-y-1.5">
              <Label htmlFor="nb-prefix">Awalan</Label>
              <Input id="nb-prefix" data-testid={NUMBERING.formPrefix} value={form.prefix}
                disabled={!canEdit} placeholder="SPK"
                onChange={(e) => setForm({ ...form, prefix: e.target.value.toUpperCase() })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nb-width">Lebar digit</Label>
              <Input id="nb-width" data-testid={NUMBERING.formWidth} type="number" min={1} max={8}
                value={form.width} disabled={!canEdit}
                onChange={(e) => setForm({ ...form, width: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nb-start">Nomor awal</Label>
              <Input id="nb-start" data-testid={NUMBERING.formStart} type="number" min={1}
                value={form.start} disabled={!canEdit}
                onChange={(e) => setForm({ ...form, start: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label>Reset urutan</Label>
              <Select value={form.reset} disabled={!canEdit}
                onValueChange={(v) => setForm({ ...form, reset: v })}>
                <SelectTrigger data-testid={NUMBERING.formReset} aria-label="Reset urutan"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {resetOptions.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Cakupan urutan</Label>
            <Select value={form.seq_scope} disabled={!canEdit}
              onValueChange={(v) => setForm({ ...form, seq_scope: v })}>
              <SelectTrigger data-testid={NUMBERING.formScope} aria-label="Cakupan urutan"><SelectValue /></SelectTrigger>
              <SelectContent>
                {scopeOptions.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="rounded-md border bg-muted/40 p-3">
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Pratinjau nomor berikutnya{projectId ? " (proyek terpilih)" : ""}</div>
            {previewError ? (
              <div data-testid={NUMBERING.previewError} className="text-sm text-destructive">{previewError}</div>
            ) : (
              <div data-testid={NUMBERING.preview} className="font-mono text-lg font-semibold">{preview}</div>
            )}
          </div>
        </div>
        <DialogFooter className="gap-2 sm:justify-between">
          <Button data-testid={NUMBERING.resetDefault} variant="ghost" size="sm"
            disabled={!canEdit || !rule.overridden} onClick={resetDefault}>
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" /> Kembalikan bawaan
          </Button>
          <div className="flex gap-2">
            <Button data-testid={NUMBERING.cancel} variant="ghost" onClick={onClose}>Tutup</Button>
            <Button data-testid={NUMBERING.submit} onClick={save}
              disabled={!canEdit || saving || !!previewError || !form.pattern}>Simpan</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
