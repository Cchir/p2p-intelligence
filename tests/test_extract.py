"""The XES reader must keep cases and events apart, and must not resolve external entities."""

from p2p import extract

XES = """<?xml version="1.0" encoding="UTF-8"?>
<log xes.version="1.0">
  <global scope="trace"><string key="concept:name" value="UNKNOWN"/></global>
  <string key="concept:name" value="demo"/>
  <trace>
    <string key="concept:name" value="A_1"/>
    <string key="Vendor" value="vendorID_0001"/>
    <boolean key="Goods Receipt" value="true"/>
    <event><string key="concept:name" value="Create Purchase Order Item"/><float key="Cumulative net worth (EUR)" value="10.0"/></event>
    <event><string key="concept:name" value="Clear Invoice"/><float key="Cumulative net worth (EUR)" value="10.0"/></event>
  </trace>
  <trace>
    <string key="concept:name" value="A_2"/>
    <event><string key="concept:name" value="Create Purchase Order Item"/></event>
  </trace>
</log>
"""


def test_parse_splits_cases_and_events(tmp_path):
    path = tmp_path / "log.xes"
    path.write_text(XES)
    traces = list(extract.parse_xes(path))
    assert [c["concept:name"] for c, _ in traces] == ["A_1", "A_2"]
    case, events = traces[0]
    assert case["Vendor"] == "vendorID_0001" and "Cumulative net worth (EUR)" not in case
    assert [e["concept:name"] for e in events] == ["Create Purchase Order Item", "Clear Invoice"]
    assert events[0]["Cumulative net worth (EUR)"] == "10.0"


def test_external_entities_are_not_expanded(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET")
    path = tmp_path / "evil.xes"
    path.write_text(
        f'<!DOCTYPE log [<!ENTITY x SYSTEM "{secret.as_uri()}">]>'
        '<log><trace><string key="concept:name" value="A"/><event><string key="a" value="&x;"/></event></trace></log>'
    )
    try:
        traces = list(extract.parse_xes(path))
    except Exception:
        return  # refusing the document outright is also safe
    assert "TOP-SECRET" not in str(traces)
