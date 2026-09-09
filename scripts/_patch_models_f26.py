#!/usr/bin/env python3
"""_patch_models_f26.py — Fase 26: pasang validator SSOT pada field enum yang masih `str` bebas.

Setiap pasangan diverifikasi HARUS terjadi tepat 1x; bila tidak, skrip gagal (anti silent-fail).
"""
import sys

PATH = "/app/backend/models.py"
PAIRS = [
    # (lama, baru)
    ('class AppointmentStatus(BaseModel):\n    status: str\n',
     'class AppointmentStatus(BaseModel):\n    status: ref.AppointmentStatusReq\n'),
    ('    body: str\n    type: str = "comment"\n',
     '    body: str\n    type: ref.ActivityType = "comment"\n'),
    ('    direction: str = "out"  # out = agent reply; in = simulated inbound (triggers automation)\n',
     '    direction: ref.MsgDirection = "out"   # in = pesan masuk (memicu automasi)\n'),
    ('    trigger_event: str = "message.received"  # message.received | lead.captured | no_response\n',
     '    trigger_event: ref.AutomationTrigger = "message.received"\n'),
    ('    name: Optional[str] = None\n    trigger_event: Optional[str] = None\n',
     '    name: Optional[str] = None\n    trigger_event: ref.OptAutomationTrigger = None\n'),
    ('    variables: Optional[List[str]] = None\n    status: Optional[str] = None  # approved | pending | rejected (simulation defaults approved)\n',
     '    variables: Optional[List[str]] = None\n    status: ref.WaTemplateStatus = None\n'),
    ('class DocumentCreate(BaseModel):\n    template_code: str = "SPR"\n',
     'class DocumentCreate(BaseModel):\n    template_code: ref.DocumentTemplate = "SPR"\n'),
    ('class DocumentSign(BaseModel):\n    role: str\n',
     'class DocumentSign(BaseModel):\n    role: ref.SignerRoleReq\n'),
    ('    unit_id: Optional[str] = None\n    result: str\n    notes: Optional[str] = None\n',
     '    unit_id: Optional[str] = None\n    result: ref.QcResultReq\n    notes: Optional[str] = None\n'),
    ('class MaterialTxn(BaseModel):\n    project_id: str\n    material_id: str\n    type: str\n',
     'class MaterialTxn(BaseModel):\n    project_id: str\n    material_id: str\n    type: ref.StockMovement\n'),
    ('class SchemeItem(BaseModel):\n    label: str\n    basis: str = "percent"  # percent | fixed\n',
     'class SchemeItem(BaseModel):\n    label: str\n    basis: ref.SchemeBasisReq = "percent"\n'),
    ('    customer_id: Optional[str] = None\n    bank_name: str\n',
     '    customer_id: Optional[str] = None\n    bank_name: ref.FinancingBankReq\n'),
    ('class FinancingUpdate(BaseModel):\n    bank_name: Optional[str] = None\n',
     'class FinancingUpdate(BaseModel):\n    bank_name: ref.FinancingBank = None\n'),
    ('    interest_rate_pct: Optional[float] = None\n    status: Optional[str] = None\n',
     '    interest_rate_pct: Optional[float] = None\n    status: ref.FinancingStatus = None\n'),
    ('class SlikUpdate(BaseModel):\n    slik_status: str  # pending | clear | flagged | rejected\n',
     'class SlikUpdate(BaseModel):\n    slik_status: ref.SlikStatusReq\n'),
    ('class PunchStatusUpdate(BaseModel):\n    status: str  # open | in_progress | verified | closed\n',
     'class PunchStatusUpdate(BaseModel):\n    status: ref.PunchStatusReq\n'),
    ('class SPKStatusUpdate(BaseModel):\n    status: str  # draft | active | completed | cancelled\n',
     'class SPKStatusUpdate(BaseModel):\n    status: ref.SpkStatusReq\n'),
    ('    label: str\n    status: str = "na"  # na | ok | issue\n',
     '    label: str\n    status: ref.SurveyCheckStatus = "na"\n'),
    ('class SurveyResult(BaseModel):\n    result: str  # recommended | needs_followup | not_recommended\n',
     'class SurveyResult(BaseModel):\n    result: ref.SurveyResultReq\n'),
    ('class TaxRecordUpdate(BaseModel):\n    status: Optional[str] = None            # pending | reported | paid\n',
     'class TaxRecordUpdate(BaseModel):\n    status: ref.TaxStatus = None\n'),
    ('    label: Optional[str] = None\n    result: Optional[str] = None   # pending | pass | fail | na\n',
     '    label: Optional[str] = None\n    result: ref.InspectionItemResult = None\n'),
    ('class InspectionCreate(BaseModel):\n    project_id: str\n    template_code: Optional[str] = None\n',
     'class InspectionCreate(BaseModel):\n    project_id: str\n    template_code: ref.InspectionTemplate = None\n'),
    # kelebihan bayar (Fase 26): kasir harus sengaja menyetujui
    ('class ReceiptCreate(BaseModel):\n    deal_id: str\n    amount: int\n    method: ref.PaymentMethod = "transfer"\n    note: Optional[str] = None\n',
     'class ReceiptCreate(BaseModel):\n    deal_id: str\n    amount: int\n    method: ref.PaymentMethod = "transfer"\n    note: Optional[str] = None\n'
     '    allow_overpay: bool = False   # True = kelebihan dicatat sbg titipan pelanggan\n'),
]


def main():
    src = open(PATH, encoding="utf-8").read()
    for old, new in PAIRS:
        n = src.count(old)
        if n != 1:
            print(f"GAGAL: pola ditemukan {n}x (harus 1x):\n---\n{old}---")
            return 1
        src = src.replace(old, new)
    open(PATH, "w", encoding="utf-8").write(src)
    print(f"OK: {len(PAIRS)} field enum models.py kini tervalidasi SSOT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
