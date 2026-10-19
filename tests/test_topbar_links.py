"""Top-bar links must be styled on a wide viewport, not only on a narrow one.

`.site-link` carried the three cross-site links in every company page's header
and its only declarations sat inside `@media(max-width:620px)`. Below 620px it
looked right; above it -- which is every desktop, and so every reviewer -- the
browser default applied: 16px, link blue, underlined, and wrapping onto a second
line because the `white-space:nowrap` was in the mobile block too. It shipped
that way on all 193 pages, and the layout test that covers this bar runs at
390px, where the bug is invisible.

So this asserts the general shape of that mistake rather than the one class: a
header link whose appearance is only ever defined for small screens.
"""

from __future__ import annotations

import inspect
import re

from company_lens.web import page
from company_lens.web.page import _css


def _topbar_link_classes() -> set[str]:
    """The classes the rendered header puts on its anchors.

    Read from the template rather than a rendered page so this needs none of the
    snapshot fixture: the question is about markup and stylesheet agreeing, and
    both are in this module.
    """
    header = re.search(r'<header class="topbar">.*?</header>', inspect.getsource(page), re.S)
    assert header, "the topbar template moved; this test can no longer find it"
    classes: set[str] = set()
    for attribute in re.findall(r'<a\b[^>]*class="([^"]+)"', header.group(0)):
        classes.update(attribute.split())
    return classes


def _unconditional_rules(css: str) -> list[tuple[str, str]]:
    """Every rule that applies with no media query in front of it.

    The stylesheet is minified onto a few long lines, so this walks it rather
    than splitting: `@media(...){` opens a block whose rules are conditional,
    and the next unmatched `}` closes it.
    """
    rules: list[tuple[str, str]] = []
    index = 0
    inside_media = False
    while index < len(css):
        opening = re.match(r"@media\([^)]*\)\{", css[index:])
        if opening:
            inside_media = True
            index += opening.end()
            continue
        if css[index] == "}" and inside_media:
            inside_media = False
            index += 1
            continue
        rule = re.match(r"([^{}@]+)\{([^{}]*)\}", css[index:])
        if not rule:
            index += 1
            continue
        if not inside_media:
            rules.append((rule.group(1), rule.group(2)))
        index += rule.end()
    return rules


def _declarations_for(css: str, class_name: str) -> dict[str, str]:
    """Properties set on `.class_name` by selectors that always apply.

    Selectors carrying a pseudo-class are skipped: `:hover` says nothing about
    how the link looks before anyone points at it.
    """
    collected: dict[str, str] = {}
    for selector, body in _unconditional_rules(css):
        for part in selector.split(","):
            part = part.strip()
            if ":" in part or not re.search(rf"\.{re.escape(class_name)}(?![\w-])", part):
                continue
            for chunk in body.split(";"):
                if ":" in chunk:
                    prop, value = chunk.split(":", 1)
                    collected[prop.strip()] = value.strip()
    return collected


def test_every_topbar_link_class_is_styled_outside_a_media_query() -> None:
    css = _css()
    unstyled = sorted(
        name
        for name in _topbar_link_classes()
        if "text-decoration" not in _declarations_for(css, name)
    )
    assert not unstyled, (
        "these header link classes have no unconditional text-decoration, so a "
        f"wide viewport renders them as default browser links: {unstyled}"
    )


def test_site_link_is_not_a_default_browser_link_on_a_wide_viewport() -> None:
    declarations = _declarations_for(_css(), "site-link")
    assert declarations.get("text-decoration") == "none", (
        "the cross-site header links are underlined above 620px"
    )
    assert "color" in declarations, (
        "the cross-site header links fall back to the browser's link blue above 620px"
    )
    # The mobile block hid them behind nowrap for a reason: "How this is audited"
    # wraps in a 70px-tall bar and pushes the row out of alignment.
    assert declarations.get("white-space") == "nowrap"
