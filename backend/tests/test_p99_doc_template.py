"""Fase 99 — template header dokumen & saran balasan (unit, tanpa DB untuk bagian murni)."""
import wa_gateway as gw
import wa_templates_meta as wtm


def test_template_payload_document_header():
    tpl = {"code": "document_delivery", "header_type": "document", "language": "id"}
    p = gw._template_payload("628123", tpl, ["Ibu", "Kwitansi", " 001", "SIPRO"],
                             {"link": "https://x/y.pdf", "filename": "kwitansi.pdf"})
    comps = p["template"]["components"]
    assert comps[0]["type"] == "header"
    assert comps[0]["parameters"][0] == {"type": "document", "document": {"link": "https://x/y.pdf", "filename": "kwitansi.pdf"}}
    assert [x["text"] for x in comps[1]["parameters"]] == ["Ibu", "Kwitansi", " 001", "SIPRO"]


def test_template_payload_media_id_preferred_when_live():
    tpl = {"code": "document_delivery", "header_type": "document"}
    p = gw._template_payload("628123", tpl, [], {"media_id": "m1", "link": None, "filename": "a.pdf"})
    assert p["template"]["components"][0]["parameters"][0]["document"] == {"id": "m1", "filename": "a.pdf"}


def test_no_header_without_header_type():
    p = gw._template_payload("628123", {"code": "welcome"}, ["A"], {"link": "x"})
    assert all(c["type"] != "header" for c in p["template"]["components"])


def test_meta_components_header_document():
    comps = wtm.meta_components({"body": "Halo {{nama}}", "variables": ["nama"], "header_type": "document"})
    assert comps[0] == {"type": "HEADER", "format": "DOCUMENT"}
    # Meta mewajibkan contoh nilai variabel (`example.body_text`) saat submit — jadi BODY boleh
    # membawa contoh; yang dijaga: tipe & teks bernomor.
    assert comps[1]["type"] == "BODY" and comps[1]["text"] == "Halo {{1}}"
    assert comps[1].get("example", {}).get("body_text"), "contoh variabel wajib disertakan untuk Meta"
    comps2 = wtm.meta_components({"body": "x", "header_type": "document", "header_sample_handle": "4::abc"})
    assert comps2[0]["example"] == {"header_handle": ["4::abc"]}
