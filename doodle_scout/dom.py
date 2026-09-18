"""A small, forgiving HTML tree built on stdlib html.parser.

Why not BeautifulSoup: this tool has to run on whatever Python is already
on the machine, with no install step. The query surface below is only as
large as the scrapers actually need.

The parser is deliberately lenient about unclosed tags, because ASP.NET
WebForms output frequently is.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}

# Tags that implicitly close a previous sibling of the same kind.
IMPLIED_CLOSE = {
    "li": {"li"},
    "tr": {"tr", "td", "th"},
    "td": {"td", "th"},
    "th": {"td", "th"},
    "p": {"p"},
    "option": {"option"},
    "dt": {"dt", "dd"},
    "dd": {"dt", "dd"},
    "thead": {"thead", "tbody", "tfoot"},
    "tbody": {"thead", "tbody", "tfoot"},
}

OPAQUE_TAGS = {"script", "style", "template", "noscript"}

_WS = re.compile(r"\s+")


def squash(text: str) -> str:
    """Collapse whitespace, including non-breaking spaces."""
    if not text:
        return ""
    return _WS.sub(" ", text.replace("\xa0", " ")).strip()


class Node:
    __slots__ = ("tag", "attrs", "children", "parent", "_data")

    def __init__(self, tag: str, attrs: dict | None = None, parent: "Node | None" = None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list["Node"] = []
        self.parent = parent
        self._data = ""  # only used by text nodes

    # -- construction ----------------------------------------------------
    @classmethod
    def text_node(cls, data: str, parent: "Node | None" = None) -> "Node":
        node = cls("#text", {}, parent)
        node._data = data
        return node

    @property
    def is_text(self) -> bool:
        return self.tag == "#text"

    # -- attribute access ------------------------------------------------
    def get(self, name: str, default: str = "") -> str:
        return self.attrs.get(name.lower(), default)

    @property
    def classes(self) -> list[str]:
        return self.get("class").split()

    def has_class(self, name: str) -> bool:
        return name.lower() in {c.lower() for c in self.classes}

    # -- text ------------------------------------------------------------
    @property
    def text(self) -> str:
        """Visible text of this subtree, whitespace-collapsed."""
        return squash(self.raw_text)

    @property
    def raw_text(self) -> str:
        if self.is_text:
            return self._data
        if self.tag in OPAQUE_TAGS:
            return ""
        return "".join(child.raw_text for child in self.children)

    @property
    def block_text(self) -> str:
        """Text with block-level boundaries preserved as newlines.

        Useful when a listing crams a whole breeder record into one cell
        separated only by <br> tags.
        """
        if self.is_text:
            return self._data
        if self.tag in OPAQUE_TAGS:
            return ""
        parts = []
        for child in self.children:
            if child.is_text:
                parts.append(child._data)
                continue
            if child.tag in ("br", "tr", "li", "p", "div", "td", "th", "hr"):
                parts.append("\n")
            parts.append(child.block_text)
            if child.tag in ("tr", "li", "p", "div"):
                parts.append("\n")
        out = "".join(parts)
        out = re.sub(r"[ \t\xa0]+", " ", out)
        out = re.sub(r" ?\n ?", "\n", out)
        return re.sub(r"\n{2,}", "\n", out).strip()

    # -- queries ---------------------------------------------------------
    def walk(self):
        for child in self.children:
            yield child
            yield from child.walk()

    def find_all(
        self,
        tag: str | tuple[str, ...] | None = None,
        *,
        attrs: dict | None = None,
        class_: str | None = None,
        id: str | None = None,
        limit: int | None = None,
    ) -> list["Node"]:
        tags = (tag,) if isinstance(tag, str) else tag
        found: list[Node] = []
        for node in self.walk():
            if node.is_text:
                continue
            if tags and node.tag not in tags:
                continue
            if id is not None and node.get("id") != id:
                continue
            if class_ is not None and not node.has_class(class_):
                continue
            if attrs:
                if not all(
                    _attr_matches(node.get(k), v) for k, v in attrs.items()
                ):
                    continue
            found.append(node)
            if limit and len(found) >= limit:
                break
        return found

    def find(self, *args, **kwargs) -> "Node | None":
        kwargs["limit"] = 1
        hits = self.find_all(*args, **kwargs)
        return hits[0] if hits else None

    def find_parent(self, tag: str | tuple[str, ...]) -> "Node | None":
        tags = (tag,) if isinstance(tag, str) else tag
        node = self.parent
        while node is not None:
            if node.tag in tags:
                return node
            node = node.parent
        return None

    # -- convenience for tabular listings --------------------------------
    def rows(self) -> list[list["Node"]]:
        """Return [[cell, ...], ...] for the nearest table structure."""
        out = []
        for tr in self.find_all("tr"):
            cells = [c for c in tr.children if not c.is_text and c.tag in ("td", "th")]
            if cells:
                out.append(cells)
        return out

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        if self.is_text:
            return f"#text({self._data[:24]!r})"
        return f"<{self.tag} {self.attrs}> children={len(self.children)}"


def _attr_matches(actual: str, expected) -> bool:
    if expected is True:
        return bool(actual)
    if callable(expected):
        return bool(expected(actual))
    if isinstance(expected, re.Pattern):
        return bool(expected.search(actual))
    return actual == expected


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#document")
        self._stack = [self.root]

    @property
    def _current(self) -> Node:
        return self._stack[-1]

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        for closes in (IMPLIED_CLOSE.get(tag) or ()):
            if any(n.tag == closes for n in self._stack[1:]):
                self._close_to(closes)
                break
        node = Node(tag, {k.lower(): (v or "") for k, v in attrs}, self._current)
        self._current.children.append(node)
        if tag not in VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        node = Node(tag, {k.lower(): (v or "") for k, v in attrs}, self._current)
        self._current.children.append(node)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in VOID_TAGS:
            return
        if any(n.tag == tag for n in self._stack[1:]):
            self._close_to(tag)

    def _close_to(self, tag: str) -> None:
        while len(self._stack) > 1:
            node = self._stack.pop()
            if node.tag == tag:
                return

    def handle_data(self, data):
        if data:
            self._current.children.append(Node.text_node(data, self._current))


def parse(html: str) -> Node:
    """Parse an HTML document into a Node tree. Never raises on bad markup."""
    builder = _TreeBuilder()
    try:
        builder.feed(html or "")
        builder.close()
    except Exception:
        # A malformed document still yields whatever was parsed before the
        # failure, which is better than nothing for a best-effort scraper.
        pass
    return builder.root
