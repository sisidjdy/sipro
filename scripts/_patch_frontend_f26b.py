#!/usr/bin/env python3
"""_patch_frontend_f26b.py — Fase 26 (lanjutan): daftar OPSI hardcode -> SSOT.

Temuan E5 bentuk kedua: `const X = [{ v: "...", l: "..." }]` yang isinya sama dengan grup
`/api/reference`. Diganti `options("grup")` / `labelOf("grup", v)` agar pilihan di UI selalu
identik dengan yang divalidasi backend.
"""
import re
import sys

FE = "/app/frontend/src/"
IMPORT_USE_REF = 'import { useReference } from "@/context/ReferenceContext";\n'

EDITS = {
    "components/appointments/AppointmentDetailSheet.js": [
        ("IMPORT:" + IMPORT_USE_REF, None),
        ('const STATUS_OPTS = [\n'
         '  { v: "scheduled", l: "Terjadwal" },\n'
         '  { v: "done", l: "Selesai" },\n'
         '  { v: "no_show", l: "Tidak Hadir" },\n'
         '  { v: "cancelled", l: "Batal" },\n'
         '];\n', ''),
        ('  const [busy, setBusy] = useState(false);\n\n'
         '  useEffect(() => { if (appointment) setStatus(appointment.status || "scheduled"); }, [appointment]);',
         '  const [busy, setBusy] = useState(false);\n'
         '  const { options } = useReference();\n\n'
         '  useEffect(() => { if (appointment) setStatus(appointment.status || "scheduled"); }, [appointment]);'),
        ('{STATUS_OPTS.map((s) => <SelectItem key={s.v} value={s.v}>{s.l}</SelectItem>)}',
         '{options("appointment_status").map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}'),
        ('<StatusPill status={appointment.status} />',
         '<StatusPill status={appointment.status} group="appointment_status" />'),
    ],
    "components/appointments/SurveyPanel.js": [
        ("IMPORT:" + IMPORT_USE_REF, None),
        ('const ITEM_STATUS = [\n'
         '  { v: "na", l: "Belum dicek" },\n'
         '  { v: "ok", l: "Baik" },\n'
         '  { v: "issue", l: "Ada masalah" },\n'
         '];\n'
         'const RESULTS = [\n'
         '  { v: "recommended", l: "Direkomendasikan" },\n'
         '  { v: "needs_followup", l: "Perlu tindak lanjut" },\n'
         '  { v: "not_recommended", l: "Tidak direkomendasikan" },\n'
         '];\n', ''),
        ('export default function SurveyPanel({ appointment, onChanged }) {\n'
         '  const [survey, setSurvey] = useState(null);',
         'export default function SurveyPanel({ appointment, onChanged }) {\n'
         '  const { options, labelOf } = useReference();\n'
         '  const [survey, setSurvey] = useState(null);'),
        ('label={ITEM_STATUS.find((s) => s.v === c.status)?.l || c.status} />',
         'label={labelOf("survey_check_status", c.status)} />'),
        ('{ITEM_STATUS.map((s) => <SelectItem key={s.v} value={s.v}>{s.l}</SelectItem>)}',
         '{options("survey_check_status").map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}'),
        ('{RESULTS.map((r) => <SelectItem key={r.v} value={r.v}>{r.l}</SelectItem>)}',
         '{options("survey_result").map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}'),
    ],
    "components/construction/InspectionsPanel.js": [
        ("IMPORT:" + IMPORT_USE_REF, None),
        ('const RESULT_OPTS = [\n'
         '  { v: "pending", l: "Belum" },\n'
         '  { v: "pass", l: "Lulus" },\n'
         '  { v: "fail", l: "Gagal" },\n'
         '  { v: "na", l: "N/A" },\n'
         '];\n', ''),
        ('function InspectionDetail({ inspection, canUpdate, onClose, onChanged }) {',
         'function InspectionDetail({ inspection, canUpdate, onClose, onChanged }) {\n'
         '  const { options, labelOf } = useReference();'),
        ('{RESULT_OPTS.map((o) => <SelectItem key={o.v} value={o.v}>{o.l}</SelectItem>)}',
         '{options("inspection_item_result").map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}'),
        ('{RESULT_OPTS.find((o) => o.v === (it.result || "pending"))?.l}',
         '{labelOf("inspection_item_result", it.result || "pending")}'),
    ],
    "components/omni/ChannelsPanel.js": [
        ("IMPORT:" + IMPORT_USE_REF, None),
        ('const CHANNEL_TYPES = [\n'
         '  { v: "whatsapp", l: "WhatsApp" },\n'
         '  { v: "meta_lead_ads", l: "Meta Lead Ads" },\n'
         '  { v: "google_lead", l: "Google Lead Form" },\n'
         '  { v: "tiktok_lead", l: "TikTok Lead" },\n'
         '  { v: "website", l: "Formulir Website" },\n'
         '];\n'
         'const CHANNEL_LABEL = Object.fromEntries(CHANNEL_TYPES.map((c) => [c.v, c.l]));\n', ''),
        ('export default function ChannelsPanel() {\n  const [rows, setRows] = useState([]);',
         'export default function ChannelsPanel() {\n'
         '  const { options, labelOf } = useReference();\n'
         '  const [rows, setRows] = useState([]);'),
        ('{CHANNEL_LABEL[c.channel] || c.channel}', '{labelOf("channel_type", c.channel)}'),
        ('<SelectContent>{CHANNEL_TYPES.map((c) => <SelectItem key={c.v} value={c.v}>{c.l}</SelectItem>)}</SelectContent>',
         '<SelectContent>{options("channel_type").map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}</SelectContent>'),
    ],
    "components/omni/RulesPanel.js": [
        ('const EVENTS = [\n'
         '  { v: "message.received", l: "Pesan masuk (keyword intent)" },\n'
         '  { v: "lead.captured", l: "Lead baru masuk" },\n'
         '  { v: "no_response", l: "Tidak ada respons (X hari)" },\n'
         '];\n'
         'const EVENT_LABEL = Object.fromEntries(EVENTS.map((e) => [e.v, e.l]));\n'
         'const ACTION_TYPES = [\n'
         '  { v: "create_task", l: "Buat tugas follow-up" },\n'
         '  { v: "send_template", l: "Kirim template WA (simulasi)" },\n'
         '  { v: "suggest_stage", l: "Usulkan majukan stage (NBA)" },\n'
         '  { v: "notify", l: "Notifikasi ke sales" },\n'
         '];\n', ''),
        ('  const { options } = useReference();', '  const { options, labelOf } = useReference();'),
        ('{EVENT_LABEL[r.trigger?.event] || r.trigger?.event}',
         '{labelOf("automation_trigger", r.trigger?.event)}'),
        ('{EVENTS.map((e) => <SelectItem key={e.v} value={e.v}>{e.l}</SelectItem>)}',
         '{options("automation_trigger").map((e) => <SelectItem key={e.value} value={e.value}>{e.label}</SelectItem>)}'),
    ],
}


def add_import(src: str, imp: str) -> str:
    if imp.strip() in src:
        return src
    last = None
    for m in re.finditer(r'^import .*?;\n', src, re.M | re.S):
        last = m
    return (src[:last.end()] + imp + src[last.end():]) if last else imp + src


def main():
    bad = []
    for rel, pairs in EDITS.items():
        path = FE + rel
        src = open(path, encoding="utf-8").read()
        for old, new in pairs:
            if old.startswith("IMPORT:"):
                src = add_import(src, old[len("IMPORT:"):])
                continue
            n = src.count(old)
            if n != 1:
                bad.append(f"{rel}: pola {n}x (harus 1x): {old[:70]!r}")
                continue
            src = src.replace(old, new)
        open(path, "w", encoding="utf-8").write(src)
        print(f"OK  {rel} ({len(pairs)} suntingan)")
    if bad:
        print("\nGAGAL:")
        for b in bad:
            print("  - " + b)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
