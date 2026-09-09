"""Patch presisi models.py: pasang tipe reference (validasi enum) per kelas+field.

Idempoten: jika field sudah memakai `ref.`, dilewati.
"""
import pathlib
import re
import sys

PATCHES = [
    ("UserCreate", "role", "    role: ref.UserRole"),
    ("UserUpdate", "role", "    role: ref.OptUserRole = None"),
    ("TaskCreate", "type", '    type: ref.TaskType = "todo"'),
    ("TaskCreate", "priority", '    priority: ref.Priority = "medium"'),
    ("TaskUpdate", "type", "    type: ref.TaskType = None"),
    ("TaskUpdate", "priority", "    priority: ref.Priority = None"),
    ("TaskUpdate", "status", "    status: ref.TaskStatus = None"),
    ("LeadCreate", "source", '    source: ref.LeadSource = "manual"'),
    ("LeadCreate", "interest_unit_type", "    interest_unit_type: ref.UnitType = None"),
    ("LeadUpdate", "interest_unit_type", "    interest_unit_type: ref.UnitType = None"),
    ("LeadStageUpdate", "stage", "    stage: ref.LeadStageReq"),
    ("AppointmentCreate", "type", '    type: ref.AppointmentType = "survey"'),
    ("WaTemplateCreate", "category", '    category: ref.WaTemplateCategory = "utility"'),
    ("WaTemplateUpdate", "category", "    category: ref.WaTemplateCategory = None"),
    ("ChannelCreate", "channel", "    channel: ref.ChannelType"),
    ("UnitGenerate", "type", '    type: ref.UnitTypeReq = "Tipe 45/90"'),
    ("MaterialCreate", "uom", '    uom: ref.Uom = "unit"'),
    ("CommissionSchemeCreate", "basis", '    basis: ref.CommissionBasis = "price"'),
    ("CommissionSchemeCreate", "trigger", '    trigger: ref.CommissionTrigger = "booked"'),
    ("ReceiptCreate", "method", '    method: ref.PaymentMethod = "transfer"'),
    ("ComplaintCreate", "category", '    category: ref.ComplaintCategory = "lainnya"'),
    ("ComplaintCreate", "priority", '    priority: ref.Priority = "medium"'),
    ("ComplaintStatusUpdate", "status", "    status: ref.ComplaintStatusReq"),
    ("PermitCreate", "type", "    type: ref.PermitTypeReq"),
    ("PermitCreate", "authority", "    authority: ref.PermitAuthority = None"),
    ("PermitUpdate", "type", "    type: ref.PermitType = None"),
    ("PermitUpdate", "authority", "    authority: ref.PermitAuthority = None"),
    ("PermitStatusUpdate", "status", "    status: ref.PermitStatusReq"),
    ("SiteDiaryCreate", "weather", "    weather: ref.Weather = None"),
    ("PunchCreate", "category", "    category: ref.WorkCategory = None"),
    ("PunchCreate", "severity", "    severity: ref.PunchSeverity = None"),
    ("PunchUpdate", "category", "    category: ref.WorkCategory = None"),
    ("PunchUpdate", "severity", "    severity: ref.PunchSeverity = None"),
    ("SubcontractorCreate", "specialty", "    specialty: ref.SubconSpecialty = None"),
    ("SubcontractorUpdate", "specialty", "    specialty: ref.SubconSpecialty = None"),
    ("BoQItemCreate", "category", '    category: ref.WorkCategory = "lainnya"'),
    ("BoQItemCreate", "uom", '    uom: ref.Uom = "unit"'),
    ("BoQItemUpdate", "category", "    category: ref.WorkCategory = None"),
    ("BoQItemUpdate", "uom", "    uom: ref.OptUom = None"),
    ("POItemIn", "uom", '    uom: ref.Uom = "unit"'),
    ("POCreate", "po_type", '    po_type: ref.PoType = "material"'),
    ("AccountCreate", "type", "    type: ref.AccountType"),
    ("InspectionCreate", "category", "    category: ref.InspectionCategory = None"),
    ("CustomerUpdate", "kyc_status", "    kyc_status: ref.KycStatus = None"),
]

path = pathlib.Path("/app/backend/models.py")
src = path.read_text()
lines = src.split("\n")

# indeks awal setiap kelas
class_at = {}
for i, ln in enumerate(lines):
    m = re.match(r"^class (\w+)\(", ln)
    if m:
        class_at[m.group(1)] = i
order = sorted(class_at.items(), key=lambda kv: kv[1])


def class_range(name):
    start = class_at[name]
    end = len(lines)
    for other, idx in order:
        if idx > start:
            end = idx
            break
    return start, end


applied, skipped, missing = 0, 0, []
for cls, field, new_line in PATCHES:
    if cls not in class_at:
        missing.append(f"{cls} (kelas tidak ada)")
        continue
    start, end = class_range(cls)
    hit = None
    for i in range(start, end):
        if re.match(rf"^    {re.escape(field)}\s*:", lines[i]):
            hit = i
            break
    if hit is None:
        missing.append(f"{cls}.{field} (field tidak ada)")
        continue
    if "ref." in lines[hit]:
        skipped += 1
        continue
    lines[hit] = new_line
    applied += 1

out = "\n".join(lines)
if "import reference as ref" not in out:
    out = out.replace(
        "from pydantic import BaseModel, EmailStr, Field",
        "from pydantic import BaseModel, EmailStr, Field\n\nimport reference as ref", 1)

path.write_text(out)
print(f"applied={applied} skipped(sudah ref)={skipped}")
if missing:
    print("TIDAK DITEMUKAN:")
    for m in missing:
        print("  -", m)
print("total lines:", len(out.split("\n")))
sys.exit(1 if missing else 0)
