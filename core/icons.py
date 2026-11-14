"""One icon set for the whole site: thin line icons drawn on a 24 x 24 grid.

`icon(name)` returns an inline SVG that takes the colour of the text around it, so one
icon looks right in a button, a heading, a tab or a dark card. `EMOJI` maps the emoji the
templates used before to the matching icon; page_head() uses it, so every page heading
gets the same kind of icon.
"""
from markupsafe import Markup

P = {
    # navigation and actions
    "home": "M3 11l9-8 9 8M5 10v10h14V10",
    "search": "M20 20l-4.2-4.2M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z",
    "x": "M6 6l12 12M18 6L6 18",
    "check": "M5 12.5l4.5 4.5L19 7.5",
    "plus": "M12 5v14M5 12h14",
    "minus": "M5 12h14",
    "arrow": "M5 12h14M13 6l6 6-6 6",
    "arrow-l": "M19 12H5M11 6l-6 6 6 6",
    "back": "M15 6l-6 6 6 6",
    "next": "M9 6l6 6-6 6",
    "up": "M12 19V5M6 11l6-6 6 6",
    "down": "M12 5v14M6 13l6 6 6-6",
    "download": "M12 4v11M7 10l5 5 5-5M5 20h14",
    "upload": "M12 16V5M7 10l5-5 5 5M5 20h14",
    "refresh": "M20 11a8 8 0 0 0-14.3-4.9L4 8M4 4v4h4M4 13a8 8 0 0 0 14.3 4.9L20 16M20 20v-4h-4",
    "edit": "M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4",
    "trash": "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
    "filter": "M4 5h16l-6 8v6l-4-2v-4z",
    "sliders": "M4 7h10M18 7h2M4 17h4M12 17h8M14 4v6M8 14v6",
    "link": "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
    "copy": "M9 9h11v11H9zM5 15H4V4h11v1",
    "eye": "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
    "logout": "M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10",
    # people and roles
    "user": "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
    "users": "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21a7 7 0 0 1 14 0M16 3.5a4 4 0 0 1 0 7.5M18 14a6 6 0 0 1 4 7",
    "teacher": "M3 4h18v11H3zM8 19l4-4 4 4M12 15v-3M7 8h6",
    "school": "M3 21h18M5 21V10l7-5 7 5v11M10 21v-5h4v5M12 9v.5",
    "building": "M4 21h16M6 21V9M10 21V9M14 21V9M18 21V9M3 9l9-6 9 6z",
    "shield": "M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z",
    "crown": "M3 8l4 4 5-7 5 7 4-4-2 11H5z",
    "hand": "M7 11V6a1.5 1.5 0 0 1 3 0v4M10 10V4.5a1.5 1.5 0 0 1 3 0V10M13 10V5.5a1.5 1.5 0 0 1 3 0V12M16 9.5a1.5 1.5 0 0 1 3 0V14a7 7 0 0 1-7 7h-1a6 6 0 0 1-5-2.7L3.5 14a1.5 1.5 0 0 1 2.5-1.6L7 14",
    "thumb-up": "M7 10v10H4V10zM7 10l4-7a2 2 0 0 1 2.5 2.2L13 9h6a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.8 20H7",
    "thumb-down": "M7 14V4H4v10zM7 14l4 7a2 2 0 0 0 2.5-2.2L13 15h6a2 2 0 0 0 2-2.3l-1.2-7A2 2 0 0 0 17.8 4H7",
    # learning
    "book": "M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5zM4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5M8 7h8",
    "book-open": "M12 6c-2-1.5-5-2-9-2v14c4 0 7 .5 9 2 2-1.5 5-2 9-2V4c-4 0-7 .5-9 2zM12 6v14",
    "cap": "M2 9l10-5 10 5-10 5zM6 11v5c3 2.5 9 2.5 12 0v-5M22 9v5",
    "exam": "M5 4h14v16H5zM9 9h6M9 13h6M9 17h3",
    "note": "M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h5",
    "notebook": "M6 3h13v18H6zM6 7H4M6 12H4M6 17H4M10 8h5",
    "flask": "M9 3h6M10 3v6L4.5 18.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3M7 15h10",
    "calc": "M6 3h12v18H6zM9 7h6M9 12h.01M12 12h.01M15 12h.01M9 16h.01M12 16h.01M15 16h.01",
    "target": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12h.01",
    "bulb": "M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z",
    "award": "M12 3a6 6 0 1 0 0 12 6 6 0 0 0 0-12zM8.5 14.5L7 22l5-3 5 3-1.5-7.5",
    "star": "M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z",
    "flame": "M12 21c-4 0-7-2.7-7-6.5 0-3.5 3-5.5 3.5-9 2 1 3.5 3 3.5 5 1-1 1.5-2.5 1.5-4 3 2 5.5 5 5.5 8 0 3.8-3 6.5-7 6.5z",
    "zap": "M13 2L4 14h7l-1 8 9-12h-7z",
    "gift": "M4 11h16v10H4zM3 7h18v4H3zM12 7v14M12 7c-1-3-5-4-5-1.5S10 7 12 7zM12 7c1-3 5-4 5-1.5S14 7 12 7z",
    # data
    "chart": "M5 20V11M12 20V4M19 20v-6",
    "trend": "M3 17l6-6 4 4 8-8M15 7h6v6",
    "list": "M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01",
    "receipt": "M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6M9 16h3",
    "globe": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c2.5 2.5 3.8 5.5 3.8 9S14.5 18.5 12 21c-2.5-2.5-3.8-5.5-3.8-9S9.5 5.5 12 3z",
    "inbox": "M3 13l3-8h12l3 8v6H3zM3 13h5l1.5 3h5L16 13h5",
    "tools": "M14.7 6.3a4 4 0 0 0-5 5L3 18l3 3 6.7-6.7a4 4 0 0 0 5-5l-2.4 2.4-2.6-.7-.7-2.6z",
    # things
    "lock": "M6 11h12v10H6zM8.5 11V7.5a3.5 3.5 0 0 1 7 0V11M12 15v2",
    "unlock": "M6 11h12v10H6zM8.5 11V7.5a3.5 3.5 0 0 1 6.8-1.2M12 15v2",
    "key": "M15 7a4 4 0 1 1-3.9 5H8v3H5v-3H3v-3h8.1A4 4 0 0 1 15 7z",
    "bell": "M6 16V11a6 6 0 1 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0",
    "mega": "M3 11v2l13 5V6zM16 9a3 3 0 0 1 0 6M6 14l1 5h3l-1-4",
    "chat": "M4 4h16v13H8l-4 4z",
    "help": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17v.5",
    "lifebuoy": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM5.6 5.6l3.6 3.6M14.8 14.8l3.6 3.6M18.4 5.6l-3.6 3.6M9.2 14.8l-3.6 3.6",
    "clip": "M20 11l-8.5 8.5a5 5 0 0 1-7-7L13 4a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L14 7",
    "cal": "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
    "clock": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
    "alert": "M12 3l10 18H2zM12 10v5M12 18v.5",
    "ban": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM5.6 5.6l12.8 12.8",
    "camera": "M4 8h3l2-3h6l2 3h3v11H4zM12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8",
    "image": "M4 5h16v14H4zM8 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM20 16l-5-5-9 8",
    "video": "M3 6h12v12H3zM15 10l6-3v10l-6-3",
    "file": "M6 3h8l4 4v14H6zM14 3v5h4",
    "excel": "M6 3h8l4 4v14H6zM14 3v5h4M9 12l5 6M14 12l-5 6",
    "mail": "M3 5h18v14H3zM3 6l9 7 9-7",
    "sun": "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
    "moon": "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
    "sparkle": "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7z",
}

FLIP = {"arrow", "arrow-l", "back", "next"}       # mirrored on right-to-left pages

EMOJI = {
    "→": "arrow", "←": "arrow-l", "↓": "down", "↑": "up",
    "✓": "check", "✔": "check", "✅": "check", "✕": "x", "✖": "x", "✘": "x", "✗": "x",
    "➕": "plus", "➖": "minus",
    "🔒": "lock", "🔐": "lock", "🔓": "unlock", "🔑": "key",
    "📚": "book", "📖": "book-open", "📓": "notebook", "🎓": "cap", "📝": "note", "✏️": "edit", "✏": "edit",
    "🧪": "flask", "🧮": "calc", "🎯": "target", "💡": "bulb", "🏅": "award", "⭐": "star", "🔥": "flame", "⚡": "zap", "🎁": "gift",
    "💬": "chat", "📢": "mega", "🔔": "bell", "🛟": "lifebuoy", "❓": "help", "🙋": "user",
    "🔁": "refresh", "🔄": "refresh", "🗑": "trash", "🗑️": "trash",
    "👥": "users", "👨‍🏫": "teacher", "🏫": "school", "🏛": "building", "🏛️": "building", "🛡️": "shield", "🛡": "shield",
    "📎": "clip", "🗓": "cal", "🗓️": "cal", "📅": "cal", "🕘": "clock", "⚠️": "alert", "⚠": "alert", "🚫": "ban", "⛔": "ban", "✋": "hand",
    "⬆️": "upload", "⬇️": "download", "📥": "inbox", "📭": "inbox",
    "🔎": "search", "🔍": "search", "📈": "trend", "📊": "chart", "🧾": "receipt", "🌐": "globe",
    "🛠️": "tools", "🛠": "tools", "👍": "thumb-up", "👎": "thumb-down", "📷": "camera", "🖼️": "image", "🖼": "image",
    "🎬": "video", "🆕": "sparkle", "🎞️": "video", "🎞": "video",
}


def icon(name, size=18, cls=""):
    name = EMOJI.get(name, name)
    d = P.get(name)
    if not d:
        return Markup('<span class="ico ico-emo">{}</span>').format(name)
    extra = (" " + cls if cls else "") + (" ico-flip" if name in FLIP else "")
    return Markup('<svg class="ico{}" width="{}" height="{}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                  'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="{}"/></svg>'
                  ).format(extra, size, size, d)
