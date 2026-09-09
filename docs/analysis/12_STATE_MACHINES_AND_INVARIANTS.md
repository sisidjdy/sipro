# SIPRO Rebuild — Dokumen 12
# STATE MACHINES & INVARIANTS (grounded ke logika SIPRO, diformalkan)

> Status: SPESIFIKASI PERILAKU. Bahasa: Indonesia.
> Format: **from → (event/guard) → to → side-effects (event + task + sync)**. Semua transisi hanya lewat aturan ini (⚑ di-gate `verify_data_integrity`).
> Asal logika: `server.py` (lead/deal/booking), `construction_router.py` (progress/QC), `documents_router.py` (dokumen).

---

## 1. LEAD LIFECYCLE (PORT server.py:891)
**States:** `acquisition → nurturing → appointment → booking → recycle` (recycle bisa balik ke acquisition/nurturing).

| from | event/guard | to | side-effects |
|---|---|---|---|
| (create) | lead.created | `acquisition` | event `lead.created` → **Task "Hubungi ≤5 mnt"** (source_event=`lead.created:{id}`), auto-assign |
| acquisition | kontak pertama (manual/WA masuk) ⚑ | `nurturing` | set `first_contacted_at` (sekali), hitung `response_time_minutes` (idempotent), Task follow-up (source_event=`lead.stage:nurturing:{id}`) |
| nurturing | appointment dibuat/di-set | `appointment` | Task siapkan survey |
| appointment | reservasi/booking dibuat | `booking` | buat/anak ke Deal draft |
| any | no-response X hari (scheduler) | `recycle` | Task re-engage (source_event=`lead.stage:recycle:{id}`), set `recycle_reason` |
| recycle | re-kontak | `nurturing`/`acquisition` | reset follow-up |

**Back-compat** status↔stage: `new↔acquisition, contacted↔nurturing, prospect↔appointment/booking, no_response/lost↔recycle`.
⚑ `response_time_minutes` dihitung **sekali** (guard: hanya bila belum ada).

---

## 2. UNIT STATUS + 3-WAY SYNC (⚑ jantung integritas)
**States:** `available → holding → reserved → booked → sold` (+ balik ke `available` bila expired/cancel).

- **holding** = hasil `find_one_and_update` atomic saat mulai reservasi (mencegah double-booking).
- Sinkron 3 arah (mirror di `units`): `deal_status` (dari deals), `construction_status`/`construction_progress` (dari construction_units), `payment_status` (dari AR).

| from | trigger | to |
|---|---|---|
| available | reserve (atomic) | holding→reserved |
| reserved | book deal | booked |
| booked | deal active (lunas DP/akad) | booked (payment naik) |
| booked/reserved | BAST/serah terima | sold |
| reserved/holding | expiry/cancel | available |

⚑ Invarian: satu unit hanya boleh punya **satu** deal berstatus aktif (`{status ∉ canceled/expired/failed}`). Enforce via unique-ish check + atomic update.

---

## 3. DEAL LIFECYCLE (PORT server.py:1136–1306)
**States:** `draft → reserved → booked → active → completed` (+ `canceled`\|`expired`\|`failed`).

| from | event/guard | to | side-effects |
|---|---|---|---|
| (create) | deal.created (unit available) | `draft` | atomic hold unit → `holding`, `reserved_until = now + BOOKING_HOLD_DAYS` |
| draft | reserve (guard: status=draft) | `reserved` | unit→`reserved`; event `deal.reserved` |
| draft/reserved | book (guard: status∈{draft,reserved}) | `booked` | unit→`booked`; **Task susun PPJB** (≤30 hari); event `deal.booked` |
| booked | aktivasi (DP lunas / PPJB signed) | `active` | AR schedule mulai; contract-liability naik |
| active | akad/serah terima selesai | `completed` | **komisi auto-create** (idempotent); event `deal.completed` |
| draft/reserved | `reserved_until < now` (scheduler sweeper) ⚑ | `expired` | unit→`available`; event `deal.expired` |
| any (≤booked) | pembatalan | `canceled` | unit→`available` |

⚑ Guard status ditegakkan (mis. "Can only reserve from draft"). Expiry sweeper = job terjadwal (Dok 13 §2).

---

## 4. RESERVATION (SPR) & PPJB PREREQUISITE
- `reservations`: `active → converted` (jadi PPJB) \| `forfeited` (booking fee hangus bila lewat `ppjb_due_at`).
- ⚑ **PPJB guard** (saat buat dokumen PPJB): butuh (a) `construction_progress ≥ 20%` **atau** flag fasum, (b) telah lewat **review pembeli 7 hari** sejak SPR, (c) dalam window **≤30 hari** sejak SPR. Bila tak terpenuhi → 400 + arahan.

## 5. FINANCING (KPR) LIFECYCLE
`draft → submitted → approved → akad` (\|`rejected`). ⚑ `disbursements` (pencairan) per milestone hanya jika `construction_progress ≥ milestone`. Reject → deal bisa `failed` atau ganti metode.

## 6. DOCUMENT LIFECYCLE (CLONE documents_router)
`draft → finalized → signed` (\|`draft → canceled`).
- draft: editable; finalize: kunci konten; sign: push signature (base64), status→`signed` di tanda tangan pertama.
- ⚑ hanya draft yang bisa diedit; hanya finalized/signed yang bisa ditandatangani; delete signed hanya ADMIN.
- Events: `document.created/finalized/signed`. BAST signed → event `unit.bast` (memicu RevRec + AJB task + retensi schedule).

## 7. CONSTRUCTION PROGRESS + QC (PORT construction_router)
- Task status: `not_started → in_progress → completed`; QC: `qc_pending → passed/failed`.
- ⚑ phase.progress = Σ(task.weight completed)/Σweight; overall = Σ(phase.progress×phase.weight/100).
- phase.status: `completed` (semua task completed/passed) \| `qc_hold` (ada failed) \| `in_progress`.
- QC fail → task `failed` → phase `qc_hold` → unit `construction_status=qc_hold`. Event `qc.passed/failed`, `construction.progress_updated`.

## 8. PROGRESS CLAIM / TERMIN (baru)
`submitted → verified → paid`. ⚑ **guard: hanya bisa `paid` bila `qc_gate_passed=true`**. Saat verified → buat `ap_bills` (net = claimed − retention), `retentions` (held). Event `progress_claim.*`.

## 9. INVARIAN GLOBAL (ringkas — detail Dok 11 §H)
1 org_id di semua koleksi · 2 unit↔deal aktif konsisten · 3 unit_id unik untuk deal aktif · 4 Σweight fase=100 · 5 AR outstanding=total−paid · 6 revenue hanya di BAST · 7 tak ada FK yatim · 8 task source_event idempotent.

> Semua state machine di atas WAJIB punya test skenario (Dok 17) & diperiksa `verify_data_integrity` di DB bersih.
