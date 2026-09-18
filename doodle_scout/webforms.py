"""Helpers for driving ASP.NET WebForms pages.

The ALAA member search is a WebForms app, so filtering and paging happen
through __doPostBack() with __VIEWSTATE round-tripped. Rather than
hardcoding control IDs (which change whenever the vendor rebuilds the
page), everything here is discovered from the live markup.
"""

from __future__ import annotations

import re

from .dom import Node

DOPOSTBACK = re.compile(
    r"__doPostBack\(\s*['\"]([^'\"]*)['\"]\s*,\s*['\"]([^'\"]*)['\"]\s*\)"
)


def form_state(doc: Node) -> dict[str, str]:
    """Every field a postback should echo back: hidden state plus the
    current value of each input, select and textarea."""
    state: dict[str, str] = {}

    for field in doc.find_all("input"):
        name = field.get("name")
        if not name:
            continue
        kind = (field.get("type") or "text").lower()
        if kind in ("submit", "button", "image", "reset", "file"):
            continue
        if kind in ("checkbox", "radio"):
            if field.get("checked") != "" or "checked" in field.attrs:
                state[name] = field.get("value") or "on"
            continue
        state[name] = field.get("value")

    for select in doc.find_all("select"):
        name = select.get("name")
        if not name:
            continue
        options = select.find_all("option")
        chosen = ""
        for option in options:
            if "selected" in option.attrs:
                chosen = _option_value(option)
                break
        if not chosen and options:
            chosen = _option_value(options[0])
        state[name] = chosen

    for area in doc.find_all("textarea"):
        name = area.get("name")
        if name:
            state[name] = area.text

    return state


def _option_value(option: Node) -> str:
    return option.get("value") if "value" in option.attrs else option.text


def postback_payload(
    doc: Node,
    target: str = "",
    argument: str = "",
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    payload = form_state(doc)
    payload["__EVENTTARGET"] = target
    payload["__EVENTARGUMENT"] = argument
    payload.setdefault("__LASTFOCUS", "")
    if overrides:
        payload.update(overrides)
    return payload


def postback_links(doc: Node) -> list[tuple[str, str, str]]:
    """(label, target, argument) for every __doPostBack link on the page."""
    out = []
    for anchor in doc.find_all(("a", "input")):
        source = anchor.get("href") or anchor.get("onclick") or ""
        match = DOPOSTBACK.search(source)
        if match:
            out.append((anchor.text or anchor.get("value"), match.group(1), match.group(2)))
    return out


def form_action(doc: Node, fallback: str) -> str:
    form = doc.find("form")
    if form is None:
        return fallback
    return form.get("action") or fallback


def select_matching_options(doc: Node, needles: set[str]) -> Node | None:
    """Find the <select> whose options best cover a set of expected values.

    Used to locate the state dropdown without knowing its control ID.
    """
    best: tuple[int, Node | None] = (0, None)
    lowered = {n.lower() for n in needles}
    for select in doc.find_all("select"):
        values = set()
        for option in select.find_all("option"):
            values.add(_option_value(option).strip().lower())
            values.add(option.text.strip().lower())
        overlap = len(values & lowered)
        if overlap > best[0]:
            best = (overlap, select)
    return best[1] if best[0] >= 5 else None


def option_values(select: Node) -> list[tuple[str, str]]:
    """(value, label) pairs, skipping empty prompts like 'Select a state'."""
    out = []
    for option in select.find_all("option"):
        value = _option_value(option).strip()
        label = option.text.strip()
        if not value or value.lower() in ("", "0", "-1", "select", "all"):
            continue
        out.append((value, label))
    return out
