# SIPRO Rebuild — Dokumen 13
# ENGINE SPEC: Event Bus · Scheduler · Guided Work Engine · Automation Rules · NBA

> Status: SPESIFIKASI MEKANIK (menutup gap Dok 09 §2B). Bahasa: Indonesia.
> Konteks stack: FastAPI + MongoDB (Motor), **tanpa broker/queue eksternal**. Semua di dalam proses backend (single service) + job terjadwal in-process. Bila skala naik → bisa pindah ke worker terpisah (tak mengubah kontrak).

---

## 1. EVENT BUS (pola OUTBOX — andal & sederhana)
**Kenapa outbox:** SIPRO sudah menulis ke `db.events` tapi **tak ada yang mengonsumsi**. Kita jadikan `events` sebagai **outbox** + **dispatcher** yang memprosesnya.

- **Emit:** setiap mutasi domain memanggil `emit(type, entity, data)` → insert `events` (`status='pending'`). Dilakukan **dalam operasi yang sama** dgn perubahan data (konsistensi).
- **Dispatch:** loop dispatcher (interval ~5–10 dtk, in-process asyncio task saat startup lifespan) mengambil `events{status:pending}` (batch, urut created_at) → panggil **handler** terdaftar per `type` → set `status='dispatched'` (atau `failed` + retry count).
- **Idempotency:** handler idempotent (mis. Guided Work Engine skip bila task `source_event` sudah open). Dispatcher aman diulang.
- **Handler registry:** `HANDLERS = {"lead.created": [gen_contact_task], "deal.booked": [gen_ppjb_task], "unit.bast": [recognize_revenue, gen_ajb_task, schedule_retention_release], "payment.paid_off": [maybe_create_commission], "message.received": [run_automation_rules], "lead.captured": [assign_and_task] , ...}`.

> Alternatif sederhana fase awal: dispatch **synchronous in-request** untuk handler ringan (buat task) + **scheduler** untuk time-based. Outbox dipakai agar tak kehilangan event bila handler gagal.

---

## 2. SCHEDULER (job terjadwal) — pilihan teknis
**Pilihan:** `APScheduler` (AsyncIOScheduler) dijalankan di FastAPI **lifespan startup** (single instance). Alternatif: asyncio loop manual. (Pilihan final dikonfirmasi saat POC.)

| Job | Cadence | Aksi |
|---|---|---|
| **Reservation expiry sweeper** | tiap 5 mnt | deals draft/reserved `reserved_until<now` → expired, unit→available (PORT server.py:1264) |
| **SLA breach check** | tiap 5 mnt | task `sla_due_at<now & open` → notifikasi + eskalasi |
| **No-response recycle** | tiap 1 jam | lead nurturing tanpa aktivitas X hari → recycle + Task |
| **AR overdue** | harian | ar_item due<now & pending → status overdue + Task collection + notif |
| **Retention release** | harian | retentions `release_due_at<now & held` → Task rilis |
| **Permit/PPJB reminder** | harian | permit/ppjb_due mendekat → notif + Task |
| **Dispatcher tick** | 5–10 dtk | proses outbox events |

⚑ Semua job **idempotent** & aman jika berjalan ganda (guard by status/timestamp). Job hasil = **event** atau **task**, bukan efek liar.

---

## 3. GUIDED WORK ENGINE (PORT shared._auto_create_task, diformalkan)
- **Aturan event→task** (tabel di Dok 03 §6.5 + Dok 08). Tiap aturan: `{on_event, task_type, title_tmpl, due_rule, assignee_rule, priority}`.
- **Idempotency:** `source_event` = `"{event.type}:{entity_id}"`; skip bila ada task open dgn source_event sama (CLONE logika SIPRO).
- **Assignee resolution:** owner record → fallback creator → fallback role default (config).
- **NBA feed:** Task Inbox mengelompokkan (overdue/today/upcoming/waiting) + SLA countdown.

---

## 4. AUTOMATION RULES ENGINE (REBUILD notifications auto_followup → nyata)
**Skema `automation_rules`:** `{trigger:{event, filter}, conditions:[{field, op, value}], actions:[...], require_confirmation}`.
- **Trigger** = tipe event (mis. `message.received`, `lead.stage_changed`, `payment.overdue`).
- **Conditions** = filter (mis. body mengandung keyword ∈ [harga, kpr, survey]).
- **Actions** = `create_lead` \| `advance_stage` \| `create_task` \| `send_template` \| `notify`.
- **Human-in-the-loop:** action `advance_stage` sensitif → default `require_confirmation=true` → jadi **NBA suggestion**, bukan otomatis (cegah salah klasifikasi).
- **Anti-loop:** action tak boleh memicu trigger sama pada entity sama dalam window pendek (guard); audit `executions`.
- **Eksekusi:** dijalankan handler `run_automation_rules` saat event relevan di-dispatch.

---

## 5. NEXT-BEST-ACTION (NBA) RULES — konkret (menutup Dok 09 gap #7)
NBA per-record = daftar 1–3 aksi berprioritas dari **resolver berbasis stage + sinyal**. Heuristik awal (tanpa LLM):

| Record | Sinyal | NBA (prioritas) |
|---|---|---|
| Lead acquisition | belum dikontak | "Hubungi sekarang" (urgent, SLA) |
| Lead nurturing | tak ada aktivitas ≥3 hari | "Follow-up (deal berisiko dingin)" |
| Lead appointment | appointment besok | "Konfirmasi & siapkan survey" |
| Deal reserved | `ppjb_due_at` H-3 | "Susun/ajukan PPJB" (high) |
| Deal booked | KPR belum diajukan | "Ajukan KPR / pra-skrining SLIK" |
| Unit construction | progress ≥ milestone KPR | "Ajukan pencairan termin" |
| AR item | overdue | "Tindak lanjut penagihan" |
| Progress claim | verified & qc pass | "Proses pembayaran termin" |
| Retention | release_due lewat | "Rilis retensi" |

- **Sumber sinyal:** field record + events + scheduler flags. **Threshold** config (mis. "dingin"=3 hari).
- **Kelayakan aksi:** setiap NBA memetakan ke **guided flow** valid (tak ada CTA mati — pelajaran Salesforce NBA).
- **Evolusi:** LLM opsional (Emergent LLM key) untuk scoring/ringkas percakapan **fase lanjut**, di atas heuristik ini.

---

## 6. GUARDRAIL ENGINE
- `verify_data_integrity`: event outbox tak menumpuk `failed`; task idempotent; scheduler idempotent.
- POC wajib (Dok 17): dispatcher+scheduler+idempotent task; jalankan seed → verifikasi task lahir sekali, expiry sweeper bekerja, automation rule memicu.
