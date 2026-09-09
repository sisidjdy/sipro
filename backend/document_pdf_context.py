"""Common issued-document amounts for staff and buyer copies; no data mutations."""
import doc_layout as dl
import contracts_engine as ce
import docgen as dg


async def layout_for_document(org, document):
    """Buyer copies use the same letterhead, footer, date and contract amounts as staff copies."""
    layout = await dl.get_layout(org, document.get("template_code") or "SPR_CASH")
    layout.setdefault("options", {})["doc_date"] = (document.get("context_snapshot") or {}).get("document_date")
    return layout, await money_rows_for_document(org, document, layout)


async def money_rows_for_document(org, document, layout):
    if not document.get("contract_id"):
        return None
    if not (dl.section_visible(layout, "biaya") or "{{tabel_biaya}}" in document.get("content", "")):
        return None
    contract = await ce.get_raw(org, document["contract_id"])
    breakdown = await ce.build_breakdown(org, contract)
    return dl.money_rows_for(layout, dg.layout_amounts(breakdown))