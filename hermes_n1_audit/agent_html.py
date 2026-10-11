"""Readable HTML from the plain text Hermes agents write (motifs, dossiers, notes).

Agents send one block of text such as « Objectif : … IMPACT : … RISQUES : … ».
The text is escaped first; only the tags built here are added.
"""

import html
import json
import re
import unicodedata

from markupsafe import Markup
from markupsafe import escape

# Folded (lowercase, no accent) label → displayed title.
LABELS = {
    "objectif": "Objectif",
    "objectifs": "Objectifs",
    "but": "But",
    "finalite": "Finalité",
    "contexte": "Contexte",
    "constat": "Constat",
    "diagnostic": "Diagnostic",
    "portee": "Portée",
    "perimetre": "Périmètre",
    "cible": "Cible",
    "motif": "Motif",
    "impact": "Impact",
    "impacts": "Impacts",
    "risque": "Risque",
    "risques": "Risques",
    "prerequis": "Prérequis",
    "preconditions": "Préconditions",
    "etapes": "Étapes",
    "plan": "Plan",
    "procedure": "Procédure",
    "actions": "Actions",
    "validation": "Validation",
    "verification": "Vérification",
    "verifications": "Vérifications",
    "controles": "Contrôles",
    "observations": "Observations",
    "retour arriere": "Retour arrière",
    "reprise": "Reprise",
    "rollback": "Retour arrière",
    "resultat": "Résultat",
    "conclusion": "Conclusion",
    "limites": "Limites",
    "comment c'est fait": "Comment c’est fait",
    "realisation": "Réalisation",
    "approche": "Approche",
}
# A label opens a section at the start of a line or after the end of a sentence,
# and must be followed by « : » then a space (so « https://… » never matches).
_ALTERNATIVES = "|".join(re.escape(k) for k in sorted(LABELS, key=len, reverse=True))
_LABEL = re.compile(rf"(?:^|(?<=[.;!?] ))({_ALTERNATIVES})\s?:(?=\s|$)")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_INLINE = re.compile(r"`([^`\n]+)`|\*\*([^*\n]+)\*\*|(https?://[^\s<>\"']+[^\s<>\"'.,;:!?)])")


def _fold(text):
    """Lowercase, accents removed, one character for one character."""
    return "".join(unicodedata.normalize("NFD", c)[0].lower() for c in text).replace("’", "'")


def _inline(text):
    out, pos = [], 0
    for m in _INLINE.finditer(text):
        out.append(escape(text[pos : m.start()]))
        code, bold, url = m.groups()
        if code is not None:
            out.append(Markup("<code>%s</code>") % code)
        elif bold is not None:
            out.append(Markup("<strong>%s</strong>") % bold)
        else:
            out.append(Markup('<a href="%s" target="_blank" rel="noopener">%s</a>') % (url, url))
        pos = m.end()
    out.append(escape(text[pos:]))
    return Markup("").join(out)


def _body(lines):
    """Paragraphs and bullet lists from a section's lines."""
    parts, para, items = [], [], []

    def flush():
        if para:
            parts.append(Markup("<p>%s</p>") % Markup("<br/>").join(_inline(x) for x in para))
            para.clear()
        if items:
            parts.append(
                Markup("<ul>%s</ul>")
                % Markup("").join(Markup("<li>%s</li>") % _inline(x) for x in items)
            )
            items.clear()

    for line in lines:
        if not line.strip():
            flush()
        elif _BULLET.match(line):
            if para:
                flush()
            items.append(_BULLET.sub("", line, count=1).strip())
        else:
            if items:
                flush()
            para.append(line.strip())
    flush()
    return Markup("").join(parts)


def agent_html(text):
    """Escaped, structured HTML for an agent's free text."""
    if not text:
        return Markup("")
    lines = []
    for line in str(text).replace("\r\n", "\n").split("\n"):
        folded, start = _fold(line), 0
        for m in _LABEL.finditer(folded):
            if line[start : m.start()].strip():
                lines.append(("text", line[start : m.start()].rstrip()))
            lines.append(("label", LABELS[m.group(1)]))
            start = m.end()
        lines.append(("text", line[start:].strip() if start else line))
    out, chunk = [], []
    for kind, value in lines:
        if kind == "label":
            out.append(_body(chunk))
            chunk = []
            out.append(Markup('<p class="mb-1 mt-2"><strong>%s</strong></p>') % value)
        else:
            chunk.append(value)
    out.append(_body(chunk))
    return Markup("").join(out)


def _plain(value, limit=200):
    if value is None or value is False:
        return "—"
    if isinstance(value, str):
        text = value
        if re.search(r"</?[a-zA-Z][^>]*>", text):
            text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    else:
        text = json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def values_table(before, after, labels=None):
    """Field | Avant | Après table; HTML values are shown as short plain text."""
    labels = labels or {}
    rows = Markup("").join(
        Markup("<tr><td>%s</td><td>%s</td><td>%s</td></tr>")
        % (
            labels.get(name, name),
            _plain((before or {}).get(name)),
            _plain((after or {}).get(name)),
        )
        for name in sorted(set(before or {}) | set(after or {}))
    )
    return (
        Markup(
            '<table class="table table-sm table-bordered mb-2"><thead><tr>'
            "<th>Champ</th><th>Avant</th><th>Après</th></tr></thead><tbody>%s</tbody></table>"
        )
        % rows
    )
