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

# Les liens ne sont suivis que vers http(s) : pas de `javascript:` ni de
# `data:` fabriqués par le modèle.
_LIEN = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_SEPARATEUR = re.compile(r":?-{2,}:?")


def _echapper(texte: str) -> str:
    return escape(texte, quote=True)


def _en_ligne(texte: str) -> str:
    """Gras, italique, code, liens — sur du texte DÉJÀ échappé.

    Le code passe en premier et son contenu est laissé intact : `**` à
    l'intérieur d'un `code` est du code, pas du gras.
    """
    morceaux = re.split(r"(`[^`]+`)", texte)
    sortie = []
    for i, m in enumerate(morceaux):
        if i % 2:
            sortie.append("<code>%s</code>" % m[1:-1])
            continue
        m = _LIEN.sub(r'<a href="\2" target="_blank">\1</a>', m)
        m = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", m)
        m = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", m)
        sortie.append(m)
    return "".join(sortie)


def html_depuis_markdown(texte: str) -> str:
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
