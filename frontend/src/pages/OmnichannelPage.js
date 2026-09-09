import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Workflow, Lock } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import RulesPanel from "@/components/omni/RulesPanel";
import TemplatesPanel from "@/components/omni/TemplatesPanel";
import BroadcastPanel from "@/components/omni/BroadcastPanel";
import ChannelsPanel from "@/components/omni/ChannelsPanel";
import PlaybookPanel from "@/components/omni/PlaybookPanel";
import CaptureFailuresPanel from "@/components/omni/CaptureFailuresPanel";
import RemindersPanel from "@/components/omni/RemindersPanel";
import { useAuth } from "@/context/AuthContext";
import api from "@/services/apiClient";
import { OMNI, P51 } from "@/constants/testIds";

/**
 * OmnichannelPage (`/automation`) — automasi percakapan, template, broadcast, channel,
 * antrean lead gagal masuk, dan **pengingat otomatis ke pembeli** (Fase 51B).
 *
 * Dua cacat yang diperbaiki saat penutupan Fase 51:
 *
 * 1. **Tab tidak bisa ditautkan.** Tab dulu `defaultValue="rules"` tanpa `?tab=`, sehingga
 *    tautan "buka Pengingat Otomatis" dari layar lain (dan muat-ulang halaman) selalu
 *    mendarat di tab Automasi. Sekarang tab dikendalikan `?tab=` seperti `/subcon`,
 *    `/materials`, dan `/finance`.
 * 2. **Halaman tampak RUSAK bagi peran yang berhak atas satu tab saja.** Manajer Keuangan
 *    punya izin `reminders` (ia yang mengejar tunggakan) tetapi TIDAK punya izin
 *    `automation_rules`/`wa_templates`. Karena tab bawaan adalah Automasi, ia selalu
 *    disambut kotak merah "Akses ditolak: tidak memiliki izin 'view' pada 'wa_templates'"
 *    — pesan benar di tempat yang salah. Sekarang tab yang tidak berizin TIDAK dirender,
 *    dan tab bawaan adalah tab pertama yang memang boleh ia buka.
 */
const TAB_DEFS = [
  { value: "rules", label: "Automasi", tid: OMNI.tabRules,
    res: "automation_rules", Comp: RulesPanel },
  { value: "templates", label: "Template WA", tid: OMNI.tabTemplates,
    res: "wa_templates", Comp: TemplatesPanel },
  { value: "broadcast", label: "Broadcast", tid: OMNI.tabBroadcast,
    res: "broadcasts", Comp: BroadcastPanel },
  { value: "playbook", label: "Playbook WA", tid: OMNI.tabPlaybook,
    res: "automation_rules", Comp: PlaybookPanel },
  { value: "channels", label: "Channel", tid: OMNI.tabChannels,
    res: "channels", Comp: ChannelsPanel },
  // Antrean gagal masuk membaca SELURUH lead organisasi (`leads:view_all`), bukan lead
  // milik sendiri — sales dengan `view_own` memang tidak boleh melihatnya.
  { value: "capture", label: "Gagal Masuk", tid: OMNI.tabCapture,
    res: "leads", act: "view_all", Comp: null },
  { value: "reminders", label: "Pengingat Otomatis", tid: P51.remindersTab,
    res: "reminders", Comp: RemindersPanel },
];

export default function OmnichannelPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const [held, setHeld] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const tabs = useMemo(
    () => TAB_DEFS.filter((t) => can(t.res, t.act || "view")), [can]);
  const canCapture = useMemo(() => tabs.some((t) => t.value === "capture"), [tabs]);

  const wanted = params.get("tab");
  const active = tabs.some((t) => t.value === wanted)
    ? wanted
    : (tabs[0]?.value || "");
  const onTab = (value) => {
    const next = new URLSearchParams();
    next.set("tab", value);
    setParams(next, { replace: false });
  };

  const loadBadge = useCallback(async () => {
    if (!canCapture) return;          // jangan memanggil pintu yang jelas tidak berizin
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/capture/failures/summary");
      setHeld(res.data?.data?.open || 0);
    } catch (e) {
      setError("Ringkasan antrean lead gagal masuk tidak bisa dimuat.");
    } finally { setLoading(false); }
  }, [canCapture]);

  useEffect(() => { loadBadge(); }, [loadBadge]);

  return (
    <div data-testid={OMNI.page} className="space-y-4">
      <div className="flex items-center gap-2">
        <Workflow className="h-5 w-5 text-primary" />
        <h1 className="page-title">Automasi &amp; Channel</h1>
        <StatusPill status="simulation" />
      </div>
      <p className="text-sm text-muted-foreground">
        Conversational engine omnichannel: aturan otomasi, template WhatsApp, akun channel,
        antrean penyelamatan lead yang gagal masuk, dan pengingat otomatis ke pembeli
        (jatuh tempo termin, tunggakan, masa garansi). Atribusi lead ke kampanye &amp; event
        CAPI pindah ke menu <strong>Marketing → Atribusi &amp; CAPI</strong> (satu urusan satu
        pintu) karena di sana angkanya bisa dipertemukan dengan biaya iklan.
        {loading ? " Memuat ringkasan…" : ""}
        {error ? ` ${error}` : ""}
        {canCapture && !loading && !error && held === 0
          ? " Belum ada lead yang tertahan di antrean gagal masuk." : ""}
      </p>

      {!tabs.length ? (
        <EmptyState icon={Lock} title="Peran Anda tidak punya akses ke automasi channel"
          description={"Automasi percakapan, template WhatsApp, broadcast, dan pengingat "
            + "otomatis dikelola peran marketing/penjualan serta keuangan. Hubungi admin "
            + "bila Anda memang perlu membukanya."} />
      ) : (
        <Tabs value={active} onValueChange={onTab} className="w-full">
          <TabsList>
            {tabs.map((t) => (
              <TabsTrigger key={t.value} data-testid={t.tid} value={t.value}>
                {t.label}
                {t.value === "capture" && held > 0 ? (
                  <span data-testid={OMNI.captureBadge}
                    className="ml-1.5 rounded-full bg-rose-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                    {held}
                  </span>
                ) : null}
              </TabsTrigger>
            ))}
          </TabsList>
          {tabs.map((t) => (
            <TabsContent key={t.value} value={t.value} className="mt-4">
              {t.value === "capture"
                ? <CaptureFailuresPanel onCountChange={setHeld} />
                : <t.Comp />}
            </TabsContent>
          ))}
        </Tabs>
      )}
    </div>
  );
}
