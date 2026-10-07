# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Reprise des membres de groupes d'appel (P4.5).

Le lien membre est passé d'une table relationnelle implicite
(``wazo_ring_group_wazo_user_rel``, créée par l'ancien ``Many2many``) à un
modèle qui porte la **priorité** de sonnerie (``wazo_ring_group_member``).
Sans reprise, les groupes déjà synchronisés perdraient leurs membres côté Odoo
— alors que le PBX, lui, les garde : la prochaine synchronisation les
effacerait donc là-bas aussi, puisque l'appel des membres remplace l'ensemble.

En ``post-migrate``, parce que la table d'arrivée n'existe qu'une fois le
modèle mis à jour. En SQL, parce qu'il n'y a pas d'historique de priorité à
reconstituer : tous les membres repris reçoivent la valeur par défaut, seul
l'ensemble importe.

L'ancienne table est **laissée en place** : c'est la donnée de retour arrière
si la mise à niveau devait être annulée. Elle est inerte — plus aucun modèle ne
la déclare.
"""

import logging

_logger = logging.getLogger(__name__)

ANCIENNE_TABLE = "wazo_ring_group_wazo_user_rel"


def migrate(cr, version):
    """Copie les liens existants, sans jamais écraser un membre déjà repris."""
    if not version:
        return  # installation neuve : rien à reprendre
    cr.execute("SELECT to_regclass(%s)", (ANCIENNE_TABLE,))
    if cr.fetchone()[0] is None:
        return
    cr.execute("""
        INSERT INTO wazo_ring_group_member
                    (group_id, user_id, priority, create_date, write_date)
        SELECT rel.group_id, rel.user_id, 10, now(), now()
          FROM wazo_ring_group_wazo_user_rel AS rel
         WHERE NOT EXISTS (
                   SELECT 1 FROM wazo_ring_group_member AS membre
                    WHERE membre.group_id = rel.group_id
                      AND membre.user_id = rel.user_id)
    """)
    if cr.rowcount:
        _logger.info(
            "wazo_phone : %d membre(s) de groupe repris depuis %s.", cr.rowcount, ANCIENNE_TABLE
        )
