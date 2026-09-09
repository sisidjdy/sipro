import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RupiahInput } from "@/components/ui/rupiah-input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import ReferenceSelect from "@/components/patterns/ReferenceSelect";
import api from "@/services/apiClient";
import { ADS } from "@/constants/testIds";

const BLANK = {
  name: "", platform: "meta", objective: "leads", status: "draft", external_id: "",
  budget_daily: "", budget_total: "", start_date: "", end_date: "", audience_note: "",
  project_ids: [],
};

/**
 * CampaignFormDialog — daftarkan / ubah kampanye.
 *
 * Aturan yang dipaksakan SERVER (bukan hanya di layar, supaya tidak bisa ditembus lewat API):
 * nama kampanye unik per platform, ID platform tidak boleh dipakai dua kampanye, dan tanggal
 * berakhir tidak boleh sebelum tanggal mulai. Pesan galatnya ditampilkan apa adanya.
 */
export default function CampaignFormDialog({ campaign, open, onOpenChange, onDone }) {
  const [form, setForm] = useState(BLANK);
  const [projects, setProjects] = useState([]);
  const [busy, setBusy] = useState(false);
  const editing = !!campaign?.id;

  const loadProjects = useCallback(async () => {
    try {
      const res = await api.get("/projects", { params: { limit: 100 } });
      setProjects(res.data.data || []);
    } catch {
      setProjects([]);  // daftar proyek opsional: form tetap bisa dipakai
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    loadProjects();
    setForm({
      ...BLANK,
      ...Object.fromEntries(Object.keys(BLANK).map((k) => [k, campaign?.[k] ?? BLANK[k]])),
      budget_daily: campaign?.budget_daily || "",
      budget_total: campaign?.budget_total || "",
      start_date: (campaign?.start_date || "").slice(0, 10),
      end_date: (campaign?.end_date || "").slice(0, 10),
      project_ids: campaign?.project_ids || [],
    });
  }, [open, campaign, loadProjects]);

  const set = (key) => (value) => setForm((f) => ({ ...f, [key]: value }));

  const submit = async () => {
    if (form.name.trim().length < 3) {
      toast.error("Nama kampanye minimal 3 karakter — tulis persis seperti di platform.");
      return;
    }
    setBusy(true);
    try {
      const body = {
        name: form.name.trim(), platform: form.platform, objective: form.objective,
        status: form.status, external_id: form.external_id.trim() || null,
        budget_daily: Number(form.budget_daily || 0), budget_total: Number(form.budget_total || 0),
        start_date: form.start_date || null, end_date: form.end_date || null,
        audience_note: form.audience_note.trim() || null,
        project_ids: form.project_ids,
      };
      if (editing) await api.put(`/ads/campaigns/${campaign.id}`, body);
      else await api.post("/ads/campaigns", body);
      toast.success(editing ? "Kampanye diperbarui." : `Kampanye “${body.name}” terdaftar.`);
      onOpenChange(false);
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan kampanye.");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={ADS.campaignForm} className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{editing ? `Ubah kampanye — ${campaign.name}` : "Kampanye baru"}</DialogTitle>
          <DialogDescription>
            Nama harus sama dengan yang dipakai di platform: itulah yang dicocokkan saat biaya
            iklan diimpor dari CSV.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="cname">Nama kampanye</Label>
            <Input id="cname" data-testid={ADS.formName} value={form.name}
              placeholder="mis. cluster-a-meta"
              onChange={(e) => set("name")(e.target.value)} />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Platform iklan</Label>
              <ReferenceSelect group="ad_platform" value={form.platform}
                onChange={set("platform")} testId={ADS.formPlatform} />
            </div>
            <div className="space-y-1.5">
              <Label>Tujuan kampanye</Label>
              <ReferenceSelect group="campaign_objective" value={form.objective}
                onChange={set("objective")} testId={ADS.formObjective} />
            </div>
            <div className="space-y-1.5">
              <Label>Status kampanye</Label>
              <ReferenceSelect group="campaign_status" value={form.status}
                onChange={set("status")} testId={ADS.formStatus} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cext">ID kampanye di platform</Label>
              <Input id="cext" data-testid={ADS.formExternalId} value={form.external_id}
                placeholder="mis. 23851000000001 (boleh kosong)"
                onChange={(e) => set("external_id")(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cbd">Anggaran harian (Rp)</Label>
              <RupiahInput id="cbd" data-testid={ADS.formBudgetDaily}
                value={form.budget_daily}
                onChange={(e) => set("budget_daily")(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cbt">Anggaran total (Rp)</Label>
              <RupiahInput id="cbt" data-testid={ADS.formBudgetTotal}
                value={form.budget_total}
                onChange={(e) => set("budget_total")(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cstart">Tanggal mulai</Label>
              <Input id="cstart" type="date" data-testid={ADS.formStart} value={form.start_date}
                onChange={(e) => set("start_date")(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cend">Tanggal berakhir</Label>
              <Input id="cend" type="date" data-testid={ADS.formEnd} value={form.end_date}
                onChange={(e) => set("end_date")(e.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Proyek yang dipromosikan</Label>
            <Select value={form.project_ids?.[0] || "__none__"}
              onValueChange={(v) => set("project_ids")(v === "__none__" ? [] : [v])}>
              <SelectTrigger data-testid={ADS.formProject} aria-label="Proyek yang dipromosikan">
                <SelectValue placeholder="Pilih proyek…" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">Semua proyek / belum ditentukan</SelectItem>
                {projects.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="caud">Catatan audiens / materi</Label>
            <Textarea id="caud" rows={2} data-testid={ADS.formAudience} value={form.audience_note}
              placeholder="mis. radius 15 km, usia 27-45, minat KPR…"
              onChange={(e) => set("audience_note")(e.target.value)} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Batal
          </Button>
          <Button data-testid={ADS.formSubmit} onClick={submit} disabled={busy}>
            {busy ? "Menyimpan…" : (editing ? "Simpan Perubahan" : "Daftarkan Kampanye")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
