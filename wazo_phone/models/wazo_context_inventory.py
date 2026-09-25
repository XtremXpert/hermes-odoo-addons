# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Inventaire des postes d'un contexte Wazo (P4.4).

Répond à une question d'exploitation que ni la liste des utilisateurs ni celle
des groupes ne couvrent : **quels numéros existent sur ce contexte, et que fait
chacun d'eux ?** Un poste peut être rattaché à une ressource qui n'a pas de
fiche Odoo (file d'attente, conférence, renvoi, parc), ou **à rien du tout** —
une orpheline, qui occupe un numéro sans que personne ne s'en serve. Ces
dernières sont invisibles partout ailleurs ; elles restent pourtant comptées
comme **prises** par le calcul de disponibilité du PBX.

Le modèle est **transitoire** : ses lignes sont reconstruites à chaque
chargement depuis le PBX, qui fait autorité. Rien n'est conservé en base, donc
rien ne peut diverger du réel — le choix déjà retenu pour les plages (§1 de la
spec), appliqué au même raisonnement.
"""

from odoo import api
from odoo import fields
from odoo import models

from ..services.wazo_client import WazoClient
from ..services.wazo_client import in_ranges
from .wazo_extension_mixin import OTHER_TYPE_LABELS

#: Libellés lisibles des rattachements. Les clés sont celles des relations de
#: l'extension — celles que connaît le mixin partagé : en ajouter une là-bas la
#: fait apparaître ici, avec un libellé de repli si cette table n'est pas
#: mise à jour.
ATTACHMENT_LABELS = {
    'user': 'Utilisateur',
    'group': "Groupe d'appel",
    'queue': "File d'attente",
    'conference': 'Salle de conférence',
    'incall': 'Renvoi entrant',
    'outcall': 'Renvoi sortant',
    'parking_lot': 'Parc de stationnement',
    'none': 'Aucun',
}


class WazoExtensionInventory(models.TransientModel):
    _name = 'wazo.extension.inventory'
    _description = "Inventaire des postes d'un contexte Wazo"
    _order = 'extension'
    _rec_name = 'extension'

    extension = fields.Char(string='Poste', required=True)
    context = fields.Char(string='Contexte')
    attachment_kind = fields.Selection(
        selection=[('user', ATTACHMENT_LABELS['user']),
                   ('none', ATTACHMENT_LABELS['none'])] + [
                       (cle, ATTACHMENT_LABELS.get(cle)
                        or cle.replace('_', ' ').capitalize())
                       for cle in OTHER_TYPE_LABELS],
        string='Rattaché à', default='none')
    attachment_label = fields.Char(
        string='Détail',
        help="Ressource qui occupe le poste. Vide avec un rattachement "
             "« Utilisateur » : la ligne existe mais n'est rattachée à "
             "personne, le poste n'est donc pas encore en service.")
    is_orphan = fields.Boolean(
        string='Orpheline', compute='_compute_is_orphan', store=True,
        help="Aucun rattachement : le numéro est pris sans que rien ne "
             "l'utilise.")
    in_declared_range = fields.Boolean(
        string='Dans une plage',
        help="Le numéro tombe dans une plage déclarée du contexte, tous types "
             "confondus.")
    odoo_reference = fields.Char(
        string='Fiche Odoo',
        help="Fiche Odoo qui tient ce poste, s'il y en a une. Ce qui "
             "distingue un poste synchronisé d'une extension laissée là.")

    @api.depends('attachment_kind')
    def _compute_is_orphan(self):
        for ligne in self:
            ligne.is_orphan = ligne.attachment_kind == 'none'

    # ------------------------------------------------------------------
    # Chargement depuis Wazo
    # ------------------------------------------------------------------

    @api.model
    def _odoo_references(self):
        """``{id de poste Wazo: « modèle, nom »}``, sans appeler le PBX.

        C'est la correspondance qui manque partout ailleurs : elle dit quelles
        extensions du contexte sont **tenues** par une fiche Odoo, et donc
        lesquelles ne le sont pas.
        """
        references = {}
        for modele in ('wazo.user', 'wazo.ring.group'):
            if modele not in self.env:
                continue
            fiches = self.env[modele].sudo().search(
                [('remote_extension_id', '!=', False)])
            for fiche in fiches:
                references[fiche.remote_extension_id] = '%s, %s' % (
                    modele, fiche.display_name)
        return references

    @api.model
    def _attachment(self, item, proprietaires):
        """Rattachement d'un poste : ``(type, détail lisible)``.

        Les ressources passent **avant** les lignes : un poste rattaché à un
        groupe, une file, une conférence, un renvoi ou un parc ne sonne chez
        personne, même si une ligne traîne à côté.
        """
        for cle in OTHER_TYPE_LABELS:
            ressource = item.get(cle)
            if ressource:
                return cle, (ressource.get('label') or ressource.get('name')
                             or str(ressource.get('uuid') or ''))
        lignes = [str(ligne.get('id')) for ligne in (item.get('lines') or [])
                  if ligne.get('id') is not None]
        if lignes:
            noms = [proprietaires[ligne] for ligne in lignes
                    if ligne in proprietaires]
            return 'user', ', '.join(noms)
        return 'none', ''

    @api.model
    def action_load(self):
        """Reconstruit l'inventaire depuis le PBX, puis rouvre la liste."""
        self.search([]).unlink()
        client = WazoClient(self.env)
        context = self.env['wazo.user']._wazo_line_context()
        reponse = client.conf('GET', '/extensions', params={'context': context})
        items = (reponse.get('items') if isinstance(reponse, dict)
                 else reponse) or []
        declarees = client.declared_ranges(context)
        toutes_plages = [plage for plages in declarees.values()
                         for plage in plages]
        # Les propriétaires ne sont demandés que si un poste a une ligne :
        # inutile d'interroger le PBX pour rien.
        proprietaires = (self.env['wazo.user']._line_owners(client)
                         if any(item.get('lines') for item in items) else {})
        miroirs = self._odoo_references()
        lignes = []
        for item in items:
            extension = str(item.get('exten') or '')
            if not extension:
                continue
            rattachement, detail = self._attachment(item, proprietaires)
            lignes.append({
                'extension': extension,
                'context': item.get('context') or context,
                'attachment_kind': rattachement,
                'attachment_label': detail,
                # Même comparaison que partout ailleurs : les bornes du PBX
                # sont **textuelles**, on compare sur la valeur numérique.
                'in_declared_range': in_ranges(extension, toutes_plages),
                'odoo_reference': miroirs.get(item.get('id')) or '',
            })
        self.create(lignes)
        return {
            'type': 'ir.actions.act_window',
            'name': "Postes du contexte",
            'res_model': 'wazo.extension.inventory',
            'view_mode': 'list,form',
            'target': 'current',
        }
