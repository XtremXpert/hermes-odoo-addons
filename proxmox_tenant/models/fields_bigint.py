# Part of the proxmox_tenant Odoo module. See LICENSE for details.
"""Champ entier en int8 : pour les octets qui dépassent int4.

``fields.Integer`` mappe sur ``int4`` (≈ 2,1 milliards) — trop juste pour
les tailles de disque et de mémoire que Proxmox rend en octets. Cette
déclinaison mappe sur ``int8`` (bigint Postgres) : même API, même
valeurs, plus de plafond. Sans cascade d'effets : le champ ne
référence rien, aucune clé étrangère ne le suit.
"""

from odoo import fields


class BigInteger(fields.Integer):
    """fields.Integer en colonne bigint — pour les octets et au-delà."""

    _column_type = ("int8", "int8")
