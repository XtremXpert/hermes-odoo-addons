# Copyright 2026 XtremXpert — AGPL-3
"""Markdown → HTML pour les réponses d'Hermes dans Discuss.

Le modèle répond en Markdown. La façade hermes.activity.repondre et
le point d'entrée discuss.channel.message_post des comptes Hermes utilisent
ce convertisseur avant de passer le résultat assaini en Markup à Odoo.
La mise en forme fonctionne ainsi aussi avec une clé API, sans session web.

ORDRE DES OPÉRATIONS, NON NÉGOCIABLE : on échappe TOUT d'abord, puis on
réintroduit soi-même les seules balises voulues. Jamais l'inverse. Le texte
vient d'un modèle de langage, donc d'une entrée non fiable : s'il produit du
HTML, on veut l'AFFICHER, pas l'exécuter. Odoo assainit de son côté, mais
un garde-fou qui dépend de celui d'en face n'est pas un garde-fou.

Portée volontairement petite : gras, italique, code, titres, listes, liens
et tableaux. Ce que le modèle produit réellement. Pas un moteur markdown.
"""

import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import quote

# Les liens ne sont suivis que vers http(s) : pas de `javascript:` ni de
# `data:` fabriqués par le modèle.
_LIEN = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_SEPARATEUR = re.compile(r":?-{2,}:?")


def _echapper(texte: str) -> str:
    return escape(texte, quote=True)


def _en_ligne(texte: str) -> str:
    """Gras, italique, code, liens — sur du texte DÉJÀ échappé.

    Le code est mis de côté d'abord et son contenu est laissé intact : `**`
    à l'intérieur d'un `code` est du code, pas du gras. Le reste est traité
    d'un seul tenant, pour qu'un gras puisse entourer du code
    (« **base `mac`** », 2026-10-15).
    """
    codes = []

    def _mettre_de_cote(m):
        codes.append("<code>%s</code>" % m[1])
        return "\x00%d\x00" % (len(codes) - 1)

    texte = re.sub(r"`([^`]+)`", _mettre_de_cote, texte.replace("\x00", ""))
    texte = _LIEN.sub(r'<a href="\2" target="_blank">\1</a>', texte)
    texte = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", texte)
    texte = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", texte)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m[1])], texte)


# Une réponse qui COMMENCE par une balise de bloc a été écrite en HTML par le
# modèle (2026-10-14 : N1 répond en <p>…</p>, Discuss montrait les balises).
# On la ramène d'abord en Markdown, puis le chemin habituel échappe tout et
# réintroduit ses balises : la règle « échapper d'abord » tient. Porté de
# hermes-agent (odoo_discuss/mise_en_forme.py) : Odoo présente, la passerelle
# transporte.
_BLOC_HTML = re.compile(r"\s*<(p|div|ul|ol|h[1-6]|table|pre|blockquote)[\s>]", re.I)


class _LecteurHtml(HTMLParser):
    """HTML simple → Markdown. Rien n'est conservé tel quel : les balises
    connues deviennent leur équivalent Markdown, les autres disparaissent en
    gardant leur texte, scripts et styles disparaissent avec leur contenu."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sortie, self.listes, self.lien, self.muet = [], [], None, 0
        self.rang, self.entete, self.tableau, self.pre = None, False, [], False

    def ecrire(self, morceau):
        if self.muet:
            return
        if self.rang is not None and self.rang:
            self.rang[-1] += morceau
        else:
            self.sortie.append(morceau)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style"):
            self.muet += 1
        elif tag in ("p", "div", "blockquote", "ul", "ol", "table"):
            self.ecrire("\n\n")
            if tag in ("ul", "ol"):
                self.listes.append(tag)
        elif tag == "br":
            self.ecrire("\n")
        elif tag == "li":
            self.ecrire("\n" + ("1. " if self.listes and self.listes[-1] == "ol" else "- "))
        elif tag in ("strong", "b"):
            self.ecrire("**")
        elif tag in ("em", "i"):
            self.ecrire("*")
        elif tag == "code":
            self.ecrire("`")
        elif tag == "pre":
            self.pre = True
            self.ecrire("\n\n```\n")
        elif re.fullmatch(r"h[1-6]", tag):
            self.ecrire("\n\n### ")
        elif tag == "a":
            href = attrs.get("href") or ""
            self.lien = href if re.match(r"https?://", href) else ""
            if self.lien:
                self.ecrire("[")
        elif tag == "tr":
            self.rang = []
        elif tag in ("td", "th"):
            self.entete = self.entete or tag == "th"
            if self.rang is not None:
                self.rang.append("")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.muet = max(0, self.muet - 1)
        elif tag in ("p", "div", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.ecrire("\n\n")
        elif tag in ("ul", "ol"):
            if self.listes:
                self.listes.pop()
            self.ecrire("\n\n")
        elif tag in ("strong", "b"):
            self.ecrire("**")
        elif tag in ("em", "i"):
            self.ecrire("*")
        elif tag == "code":
            self.ecrire("`")
        elif tag == "pre":
            self.pre = False
            self.ecrire("\n```\n\n")
        elif tag == "a" and self.lien:
            self.ecrire("](%s)" % self.lien)
            self.lien = None
        elif tag == "tr" and self.rang is not None:
            cellules, self.rang = [" ".join(c.split()) for c in self.rang], None
            self.sortie.append("\n| " + " | ".join(cellules) + " |")
            if self.entete and not self.tableau:
                self.sortie.append("\n|" + "---|" * len(cellules))
            self.tableau.append(cellules)
        elif tag == "table":
            self.tableau, self.entete = [], False
            self.ecrire("\n\n")

    def handle_data(self, data):
        if self.rang is not None and self.rang:
            self.rang[-1] += data
        else:
            self.ecrire(data if self.pre else re.sub(r"\s+", " ", data))


def markdown_depuis_html(texte: str) -> str:
    lecteur = _LecteurHtml()
    lecteur.feed(texte)
    lecteur.close()
    texte = "".join(lecteur.sortie)
    # Lignes nettes : pas d'espace en tête de ligne, pas plus d'une ligne vide.
    texte = "\n".join(ligne.strip() for ligne in texte.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", texte).strip()


def html_depuis_markdown(texte: str) -> str:
    if _BLOC_HTML.match(texte or ""):
        texte = markdown_depuis_html(texte)
    lignes = _echapper(texte or "").split("\n")
    html, para, tableau = [], [], []
    liste = None
    code = None

    def vider_para():
        if para:
            html.append("<p>%s</p>" % _en_ligne("<br>".join(para)))
            del para[:]

    def fermer_liste():
        nonlocal liste
        if liste:
            html.append("</%s>" % liste)
            liste = None

    def vider_tableau():
        if not tableau:
            return
        rangs = [[c.strip() for c in ligne.strip("|").split("|")] for ligne in tableau]
        # Un vrai tableau markdown a une ligne de séparation en deuxième
        # position. Sans elle, ce sont des lignes qui commencent par « | » —
        # on les rend en paragraphe plutôt que d'inventer un tableau.
        vrai = len(rangs) > 1 and all(_SEPARATEUR.fullmatch(c) for c in rangs[1] if c)
        if vrai:
            sortie = ['<table class="table table-sm table-bordered mb-2"><thead><tr>']
            sortie += ["<th>%s</th>" % _en_ligne(c) for c in rangs[0]]
            sortie.append("</tr></thead><tbody>")
            for rang in rangs[2:]:
                sortie.append("<tr>")
                sortie += ["<td>%s</td>" % _en_ligne(c) for c in rang]
                sortie.append("</tr>")
            sortie.append("</tbody></table>")
            html.append("".join(sortie))
        else:
            para.extend(tableau)
            vider_para()
        del tableau[:]

    for ligne in lignes:
        # Bloc de code : rien n'est interprété tant qu'il n'est pas fermé.
        if code is not None:
            if ligne.strip().startswith("```"):
                html.append("<pre><code>%s</code></pre>" % "\n".join(code))
                code = None
            else:
                code.append(ligne)
            continue
        if ligne.strip().startswith("```"):
            vider_tableau()
            vider_para()
            fermer_liste()
            code = []
            continue

        if ligne.strip().startswith("|"):
            vider_para()
            fermer_liste()
            tableau.append(ligne.strip())
            continue
        vider_tableau()

        if not ligne.strip():
            vider_para()
            fermer_liste()
            continue

        titre = re.match(r"(#{1,6})\s+(.*)", ligne)
        if titre:
            vider_para()
            fermer_liste()
            # On décale vers le bas : un h1 dans un fil de discussion écrase
            # tout ce qui l'entoure. Le plus gros titre d'Hermes est un h3.
            niveau = min(len(titre.group(1)) + 2, 6)
            html.append("<h%d>%s</h%d>" % (niveau, _en_ligne(titre.group(2)), niveau))
            continue

        puce = re.match(r"\s*[-*+]\s+(.*)", ligne)
        numero = re.match(r"\s*\d+[.)]\s+(.*)", ligne)
        if puce or numero:
            voulu = "ul" if puce else "ol"
            if liste != voulu:
                vider_para()
                fermer_liste()
                html.append("<%s>" % voulu)
                liste = voulu
            html.append("<li>%s</li>" % _en_ligne((puce or numero).group(1)))
            continue

        fermer_liste()
        para.append(ligne)

    if code is not None:  # bloc jamais fermé : on rend ce qu'on a
        html.append("<pre><code>%s</code></pre>" % "\n".join(code))
    vider_tableau()
    vider_para()
    fermer_liste()
    return "".join(html)


# ── Boutons d'approbation ────────────────────────────────────────────────
# Repris de hermes-agent (odoo_discuss/mise_en_forme.py, Bemade Inc., AGPL-3).
# Le framework Hermes demande ses approbations en texte :
#   « Reply `/approve` to execute, `/approve session` to approve this pattern
#     for the session, `/approve always` to approve permanently, or `/deny`
#     to cancel. »
# Odoo remplace cette phrase par des boutons. Chacun mène à /hermes/repondre
# (controllers/main.py), qui poste la commande AU NOM DE LA PERSONNE QUI
# CLIQUE : la garde d'auteur de Hermes la valide comme un message tapé.
# Liens RELATIFS : l'URL interne qu'utilise l'agent (http://maison:8069)
# n'est pas joignable depuis le navigateur d'un humain.
_INVITE_APPROBATION = re.compile(
    r"Reply\s+`(?P<p>[/!.]?)approve`\s+to\s+execute[\s\S]{0,200}?`(?P=p)deny`\s+to\s+cancel\.?"
)


def _bouton(base, prefixe, cmd, couleur, etiquette):
    # Classes plutôt que styles : le nettoyeur d'Odoo retire `gap` et
    # `background`, pas les classes Bootstrap. o_hermes_approve est le
    # marqueur que static/src/approval.esm.js intercepte.
    href = base + quote(prefixe + cmd, safe="")
    return (
        f'<a class="btn {couleur} btn-sm me-2 mb-1 o_hermes_approve" href="{escape(href)}">'
        f"{etiquette}</a>"
    )


def remplacer_invite_approbation(texte, canal_id):
    """Rend (texte sans l'invite, HTML des boutons), ou (texte, "") sans invite.

    S'applique au texte BRUT, avant la conversion : les accents graves y sont
    encore. Les commandes à taper restent écrites sous les boutons : la mise
    en forme ne retire jamais un moyen d'agir.
    """
    m = _INVITE_APPROBATION.search(texte or "")
    if not m:
        return texte, ""
    prefixe = m.group("p") or "/"
    base = "/hermes/repondre?canal=%d&cmd=" % int(canal_id)
    boutons = (
        '<div class="o_hermes_approval border rounded-3 p-2 mt-1" style="border-color:#e0a800">'
        + _bouton(base, prefixe, "approve", "btn-success", "✅&nbsp;Approuver")
        + _bouton(base, prefixe, "approve session", "btn-outline-secondary", "Pour la session")
        + _bouton(base, prefixe, "approve always", "btn-outline-secondary", "Toujours (permanent)")
        + _bouton(base, prefixe, "deny", "btn-outline-danger", "❌&nbsp;Refuser")
        + '<div class="mt-1"><small class="text-muted">'
        + "ou répondre <code>{p}approve</code>, <code>{p}approve&nbsp;session</code>, "
        "<code>{p}approve&nbsp;always</code>, <code>{p}deny</code>".format(p=escape(prefixe))
        + "</small></div></div>"
    )
    return (texte[: m.start()] + texte[m.end() :]).strip(), boutons


def html_reponse(texte, canal_id):
    """Réponse d'agent complète : boutons d'approbation, puis mise en forme."""
    texte, boutons = remplacer_invite_approbation(texte, canal_id)
    return html_depuis_markdown(texte) + boutons
