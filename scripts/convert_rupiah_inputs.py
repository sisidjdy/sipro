"""Konversi <Input type="number"> nominal Rupiah → <RupiahInput> (sekali jalan)."""
import re
import sys

ROOT = "/app/frontend/src/"
TARGETS = """
components/subcon/ChangeOrdersSection.js:117
components/subcon/AdvancesPanel.js:291,395
components/subcon/AddSPKDialog.js:72
components/subcon/AddScopeItemsDialog.js:148
components/boq/AddBoQItemDialog.js:60
components/portal/PaymentProofDialog.js:95
components/ads/SpendEntryDialog.js:117
components/ads/CampaignFormDialog.js:129,135
components/config/AddonPanel.js:181
components/config/AllinSchemePanel.js:70,130
components/config/UnitTypePanel.js:161
components/config/PriceComponentPanel.js:144
components/config/PaymentSchemePanel.js:363
components/config/KprDisbursementSchemePanel.js:92
components/config/PricingRuleDialog.js:119
components/vendors/PriceListPanel.js:258
components/pettyCash/SettleAdvanceDialog.js:92
components/pettyCash/DisburseAdvanceDialog.js:60
components/pettyCash/RequestAdvanceDialog.js:78
components/procurement/PODetailSheet.js:173
components/procurement/AddPODialog.js:153
components/budget/BudgetItemDialog.js:159
components/budget/ReviseDialog.js:58
components/budget/ManualEntryDialog.js:60
components/budget/TargetDialog.js:219,224
components/tax/WithholdingIssueDialog.js:127
components/tax/WithholdingActionDialog.js:89
components/tax/FakturActionDialog.js:93
components/fixedAssets/AddAssetDialog.js:133,138
components/fixedAssets/DisposeAssetDialog.js:59
components/materials/ReqToPoDialog.js:120
components/projects/EditUnitDialog.js:85
components/projects/StructureTab.js:416
components/master/docLayout/RowsForm.js:80
components/marketingFee/PayFeeDialog.js:56
components/marketingFee/SubmitFeeDialog.js:122
components/contracts/CostBillingPanel.js:150
components/pricing/AllinSchemeField.js:91
components/labor/WorkerDialog.js:87
components/partners/FeeRuleFormDialog.js:278
components/finance/ConfigPanel.js:126
components/finance/DepositPanel.js:202,264
components/finance/ReceiptDialog.js:84
components/finance/SchemeDialogs.js:192,194
components/finance/BankAccountDialog.js:111
components/finance/ApPanel.js:204,328,360
components/gl/AddJournalDialog.js:125,130
components/sales/ReserveDialog.js:157,170
components/sales/BookingFeePanel.js:127
components/sales/BookingFeeExtras.js:106
components/loans/PayInstallmentDialog.js:68
components/loans/AddLoanDialog.js:99,114
components/customers/FinancingDialogs.js:90,92,235
pages/ProjectsPage.js:345
pages/UnitDetailPage.js:312,326
"""
ATTR_RE = re.compile(r'\s+(type|min|max|step|inputMode)=("[^"]*"|\{[^{}]*\})')
IMPORT = 'import { RupiahInput } from "@/components/ui/rupiah-input";\n'


def convert(path, lines_1based):
    src = open(path).read()
    lines = src.split("\n")
    # proses dari bawah agar nomor baris tetap valid
    for ln in sorted(lines_1based, reverse=True):
        i = ln - 1
        start = next(k for k in range(i, i - 4, -1) if "<Input" in lines[k])
        col = lines[start].index("<Input")
        # cari akhir tag "/>"
        end = start
        while "/>" not in lines[end][(col if end == start else 0):]:
            end += 1
        tag_text = "\n".join([lines[start][col:]] + lines[start + 1:end + 1])
        cut = tag_text.index("/>") + 2
        tag, rest = tag_text[:cut], tag_text[cut:]
        assert 'type="number"' in tag, (path, ln, tag[:80])
        tag = tag.replace("<Input", "<RupiahInput", 1)
        tag = ATTR_RE.sub("", tag)
        new = (lines[start][:col] + tag + rest).split("\n")
        lines[start:end + 1] = new
    out = "\n".join(lines)
    if "RupiahInput }" not in out:
        out = out.replace('import { Input } from "@/components/ui/input";\n',
                          'import { Input } from "@/components/ui/input";\n' + IMPORT, 1)
        assert IMPORT in out, path
    if "<Input" not in out:
        out = out.replace('import { Input } from "@/components/ui/input";\n', "", 1)
    open(path, "w").write(out)
    return len(lines_1based)


total = 0
for row in TARGETS.strip().splitlines():
    f, nums = row.split(":")
    total += convert(ROOT + f, [int(n) for n in nums.split(",")])
print("converted", total)
