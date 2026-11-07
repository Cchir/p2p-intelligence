"""Extract: stream the XES event log into two untouched "bronze" parquet files.

XES is XML, and this file is ~730 MB, so it is read element by element and cleared as it goes
rather than loaded into memory. Case-level attributes go to one file, events to the other.
Entity resolution and network access are disabled in the parser: the input is external data.
"""

from __future__ import annotations

import hashlib
import logging

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from lxml import etree

from p2p import config

log = logging.getLogger(__name__)
BATCH = 200_000


def _md5(path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def download(force: bool = False) -> None:
    config.ensure_dirs()
    if force or not config.SOURCE_XES.exists():
        log.info("downloading %s", config.SOURCE_URL)
        with requests.get(config.SOURCE_URL, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(config.SOURCE_XES, "wb") as f:
                for chunk in r.iter_content(1 << 22):
                    f.write(chunk)
    digest = _md5(config.SOURCE_XES)
    if digest != config.SOURCE_MD5:
        raise ValueError(f"checksum mismatch for {config.SOURCE_XES.name}: {digest}")
    log.info("checksum verified (%s)", digest)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attrs(element) -> dict:
    """The child <string/date/...> attribute elements of a trace or event, as key -> value."""
    return {c.get("key"): c.get("value") for c in element if _local(c.tag) not in ("event", "trace")}


def parse_xes(path):
    """Yield (case_attrs, [event_attrs, ...]) for each trace, keeping memory flat."""
    context = etree.iterparse(str(path), events=("end",), resolve_entities=False, no_network=True, huge_tree=True)
    for _, el in context:
        if _local(el.tag) != "trace":
            continue
        events = [_attrs(c) for c in el if _local(c.tag) == "event"]
        yield _attrs(el), events
        el.clear()
        while el.getprevious() is not None:
            del el.getparent()[0]


def _writer_batch(rows: list[dict], writer, path):
    table = pa.Table.from_pylist(rows)
    # All columns stay text in bronze: typing is a transform decision, and this keeps the schema stable.
    table = table.cast(pa.schema([(f.name, pa.string()) for f in table.schema]))
    if writer is None:
        writer = pq.ParquetWriter(path, table.schema, compression="zstd")
    else:
        table = table.select(writer.schema.names)
    writer.write_table(table)
    return writer


def to_bronze(force: bool = False) -> None:
    if config.BRONZE_CASES.exists() and config.BRONZE_EVENTS.exists() and not force:
        log.info("bronze parquet already present")
        return
    case_w = event_w = None
    cases, events, n_cases, n_events = [], [], 0, 0
    case_keys: list[str] = []
    event_keys: list[str] = []

    def flush():
        nonlocal case_w, event_w, case_keys, event_keys
        if not case_keys:
            case_keys = sorted({k for r in cases for k in r})
            event_keys = sorted({k for r in events for k in r})
        case_w = _writer_batch([{k: r.get(k) for k in case_keys} for r in cases], case_w, config.BRONZE_CASES)
        event_w = _writer_batch([{k: r.get(k) for k in event_keys} for r in events], event_w, config.BRONZE_EVENTS)
        cases.clear()
        events.clear()

    for case, evs in parse_xes(config.SOURCE_XES):
        cid = case.get("concept:name")
        cases.append(case)
        for i, e in enumerate(evs):
            e = dict(e, case_id=cid, event_seq=str(i))
            events.append(e)
        n_cases += 1
        n_events += len(evs)
        if len(events) >= BATCH:
            flush()
    if cases:
        flush()
    case_w.close()
    event_w.close()
    log.info("bronze: %s cases, %s events", f"{n_cases:,}", f"{n_events:,}")


def run(force: bool = False) -> None:
    download(force=force)
    to_bronze(force=force)
