# Part of the voipms_sms Odoo module. See LICENSE for details.
"""Segmentation et normalisation des SMS.

Contrats validés en production (canal VoIP.ms REST v1) :
- les appels ``sendSMS`` de plus de ~150 caractères sont rejetés ;
- les segments numérotés « i/n texte » (≤ 150 caractères) sont acceptés ;
- les numéros NANP sont normalisés sur 11 chiffres (préfixe 1) ;
- message vide ou > 1600 caractères : rejet local avant tout appel.
"""

import re

MAX_SEGMENT = 150
MAX_GLOBAL = 1600
SEGMENT_PREFIX_LEN = 4  # « 9/9 »


def normalize_nanp(value):
    """Normalise un numéro NANP en 11 chiffres (préfixe 1).

    Lève ValueError pour toute entrée non-NANP (vide, longueurs
    intermédiaires, indicatif international autre que +1).
    """
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 10:
        digits = "1" + digits
    if len(digits) != 11 or not digits.startswith("1"):
        raise ValueError("Numéro NANP invalide : %s" % (value,))
    return digits


def _segment_count(total_len):
    for n in range(1, 21):
        body = MAX_SEGMENT - len("%d/%d " % (n, n))
        if n * body >= total_len:
            return n
    raise ValueError("Message trop long pour être segmenté.")


def split_sms(text):
    """Découpe ``text`` en segments de ≤ 150 caractères, numérotés.

    Le découpage se fait sur des limites de mots pour ne pas casser
    les mots. Lève ValueError si le texte est vide ou > MAX_GLOBAL.
    """
    text = " ".join(str(text or "").split())
    if not text:
        raise ValueError("Message vide.")
    if len(text) > MAX_GLOBAL:
        raise ValueError("Message de %d caractères, maximum %d." % (len(text), MAX_GLOBAL))
    if len(text) <= MAX_SEGMENT:
        return [text]
    total = len(text)
    count = _segment_count(total)
    body_len = MAX_SEGMENT - len("%d/%d " % (count, count))
    # Découpage glouton sur les limites de mots.
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= body_len:
            chunks.append(remaining)
            break
        cut = remaining.rfind(" ", 0, body_len)
        if cut <= 0:  # mot plus long qu'un segment : coupure dure
            cut = body_len
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if len(chunks) != count:  # sécurité : le comptage et le découpage divergent
        count = len(chunks)
    return ["%d/%d %s" % (i, count, chunk) for i, chunk in enumerate(chunks, start=1)]
