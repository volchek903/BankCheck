from __future__ import annotations

from html import escape


def html_escape(value: object | None) -> str:
    return escape("" if value is None else str(value), quote=False)


def bold(value: object | None) -> str:
    return f"<b>{html_escape(value)}</b>"


def source_line(source: str) -> str:
    return f"{bold('Источник:')} {html_escape(source)}"


def notice_block(title: str, items: list[str], limit: int) -> list[str]:
    if not items:
        return []

    lines = [bold(title)]
    lines.extend(f"  • {html_escape(item)}" for item in items[:limit])
    lines.append("")
    return lines
