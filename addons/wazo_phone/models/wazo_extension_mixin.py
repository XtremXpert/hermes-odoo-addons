# Part of the wazo_phone Odoo module. See LICENSE for details.
"""Contrôle et recherche d'un poste Wazo — commun aux utilisateurs et aux groupes.

``wazo.user`` et ``wazo.ring.group`` prennent tous deux un **poste** (une
extension) dans une plage déclarée du contexte. Les règles sont identiques :

* le numéro doit être numérique et ne pas être déjà porté par une autre fiche
  (dans l'un **ou** l'autre des deux modèles) ;
* il doit tomber dans la plage déclarée pour **son** type, et non dans celle
  d'un autre type (la plage des groupes est réservée aux groupes, même vide) ;
* il ne doit pas être déjà occupé côté Wazo — ni rattaché à un objet d'un autre
  type, ni en service chez un utilisateur, ni rester en ressource résiduelle ;
* une reprise n'est légitime qu'après un échec constaté (état ``error``).

Seul ``_extension_type`` distingue les deux modèles. Les dupliquer garantirait
une dérive entre les deux copies ; d'où ce mixin.

**Contrat pour les modèles concrets** : ils portent ``extension`` (fourni ici),
``wazo_state`` (états ``new`` / ``synced`` / ``error``) et un champ
``error_message``.
"""

import logging
import re

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

from ..services.wazo_client import WazoAPIError
from ..services.wazo_client import WazoClient
from ..services.wazo_client import in_ranges

_logger = logging.getLogger(__name__)

#: Libellés des types d'objets pouvant occuper une extension, pour des refus
#: lisibles. Les clés sont celles des relations de la définition ``Extension``
#: de l'API (``ExtensionRelationGroup``, ``ExtensionRelationQueue``, …).
OTHER_TYPE_LABELS = {
    'group': "un groupe d'appel",
    'queue': "une file d'attente",
    'conference': 'une salle de conférence',
    'incall': 'un renvoi entrant',
    'outcall': 'un renvoi sortant',
    'parking_lot': 'un parc de stationnement',
}

#: Libellés des types de plages, pour nommer ce à quoi un numéro est réservé.
RANGE_TYPE_LABELS = {
    'user': 'postes',
    'group': "groupes d'appel",
    'queue': "files d'attente",
    'conference': 'salles de conférence',
    'incall': 'renvois entrants',
}

#: Modèles se disputant un même poste, avec le **destinataire du refus** —
#: préposition comprise, pour que la phrase reste correcte : « attribué **au**
#: groupe » et non « à le groupe ».
EXTENSION_HOLDERS = {
    'wazo.user': "à l'utilisateur Wazo « %s »",
    'wazo.ring.group': "au groupe d'appel « %s »",
}


class WazoExtensionMixin(models.AbstractModel):
    _name = 'wazo.extension.mixin'
    _description = 'Poste Wazo (base commune utilisateurs et groupes)'

    #: Type de plage dont ce poste doit relever (``user``, ``group``…).
    _extension_type = 'user'

    extension = fields.Char(
        string='Poste',
        help='Poste téléphonique (chiffres), pris dans la plage déclarée pour '
             'ce type côté Wazo.')

    # ------------------------------------------------------------------
    # Règles locales (aucun appel réseau)
    # ------------------------------------------------------------------

    @api.constrains('extension')
    def _check_extension_local(self):
        """Le poste doit être numérique, et libre au sein d'Odoo.

        L'unicité est vérifiée sur **les deux** modèles qui se partagent le
        plan de numérotation : un poste d'utilisateur et un numéro de groupe ne
        peuvent pas coïncider, même si les plages ont été mal déclarées côté
        Wazo.

        Règles locales seulement : aucune requête vers le PBX n'a sa place dans
        une contrainte, qui s'exécute à chaque écriture et par lots. Le contrôle
        des plages se fait à la synchronisation, avant toute écriture distante.
        """
        for record in self:
            extension = record.extension or ''
            if not extension:
                # Le poste reste facultatif : c'est la synchronisation qui
                # l'exige explicitement.
                continue
            if not re.fullmatch(r'[0-9]+', extension):
                raise ValidationError(
                    'Le poste « %s » doit être composé de chiffres uniquement.'
                    % extension)
            for modele, libelle in EXTENSION_HOLDERS.items():
                if modele not in self.env:
                    # Modèle absent (installation partielle) : rien à vérifier.
                    continue
                domaine = [('extension', '=', extension)]
                if modele == record._name:
                    domaine.append(('id', '!=', record.id))
                detenteur = self.env[modele].search(domaine, limit=1)
                if detenteur:
                    raise ValidationError(
                        'Le poste %s est déjà attribué %s dans Odoo.'
                        % (extension, libelle % detenteur.name))

    # ------------------------------------------------------------------
    # Côté Wazo
    # ------------------------------------------------------------------

    def _wazo_tenant_uuid(self):
        """Tenant Wazo visé par cette fiche.

        Un tenant n'en connaît qu'un : celui de ses réglages. Le module
        serveur (``wazo_server``) étend ce point pour viser le tenant **choisi
        sur la fiche**, ce qui permet d'administrer plusieurs tenants depuis
        une même instance : chaque appel part alors avec l'en-tête
        ``Wazo-Tenant`` du bon tenant.
        """
        return (self.env['ir.config_parameter'].sudo()
                .get_str('wazo.tenant_id') or None)

    def _wazo_client(self):
        """Client Wazo dans le contexte du tenant visé par cette fiche."""
        return WazoClient(self.env, tenant_id=self._wazo_tenant_uuid())

    def _wazo_line_context(self):
        """Contexte Asterisk où vivent les postes (paramètre système)."""
        return (self.env['ir.config_parameter'].sudo()
                .get_str('wazo.line_context', default='default') or 'default')

    def _find_wazo_extension(self, client):
        """Retourne l'extension Wazo du poste, ou ``None``.

        Parcours complet de la liste avec matching en Python : robuste, ne
        dépend pas du filtre serveur (certaines versions ne retournent pas la
        liste filtrée attendue). Coût : une requête, négligeable pour la taille
        d'un PBX.

        confd 26 renvoie ``{'total': N, 'items': [...]}`` ; on tolère aussi une
        liste nue (tests, versions antérieures).
        """
        result = client.conf('GET', '/extensions')
        # Un if/else se lit mieux ici que l'expression conditionnelle que
        # suggère la règle : le cas « liste nue » mérite sa propre ligne.
        if isinstance(result, dict):  # noqa: SIM108
            items = result.get('items') or []
        else:
            items = result or []
        for ext in items:
            if str(ext.get('exten', '')) == str(self.extension):
                return ext
        return None

    def _line_owners(self, client):
        """Table ``{id de ligne: nom de l'utilisateur}``, en **un** appel.

        ``GET /users`` rend les lignes de tous les utilisateurs : une requête
        suffit là où un ``GET /lines/{id}`` par ligne en demanderait plusieurs.
        Appelable sur un jeu vide (l'inventaire n'est rattaché à aucune fiche).
        """
        resultat = client.conf('GET', '/users')
        utilisateurs = (resultat.get('items')
                        if isinstance(resultat, dict) else resultat) or []
        proprietaires = {}
        for utilisateur in utilisateurs:
            nom = ' '.join(part for part in (utilisateur.get('firstname'),
                                             utilisateur.get('lastname'))
                           if part) or str(utilisateur.get('id') or '?')
            for ligne in (utilisateur.get('lines') or []):
                if ligne.get('id') is not None:
                    proprietaires[str(ligne['id'])] = nom
        return proprietaires

    def _extension_owner(self, client, existing):
        """Nom de l'utilisateur qui occupe déjà le poste, s'il y en a un.

        Une extension peut exister sans être **en service** : ressource
        résiduelle d'un objet supprimé, ou extension créée puis abandonnée.
        Ce qui la met en service, c'est une **ligne rattachée à un
        utilisateur** — le poste sonne alors chez quelqu'un.

        Retourne une chaîne vide quand personne n'occupe la ligne — et
        n'interroge pas le PBX dans ce cas.
        """
        lignes = [str(ligne.get('id')) for ligne in (existing.get('lines') or [])
                  if ligne.get('id') is not None]
        if not lignes:
            return ''
        proprietaires = self._line_owners(client)
        return next((proprietaires[ligne] for ligne in lignes
                     if ligne in proprietaires), '')

    def _check_extension_allowed(self, client, context, existing):
        """Refuse un poste hors plage, réservé à un autre type, ou déjà pris.

        Appelée juste avant toute écriture distante : son verdict est un
        ``UserError``, donc un message visible — et rien n'a été créé sur Wazo.

        ``existing`` est le poste déjà présent côté Wazo (``None`` sinon) :

        * rattaché à **un groupe, une file, une conférence, un renvoi ou un
          parc**, c'est un refus sans ambiguïté — jamais une reprise ;
        * rattaché à une **ligne en service**, c'est un refus également : le
          poste sonne chez quelqu'un ;
        * présent **sans aucun rattachement**, c'est une ressource résiduelle ;
        * mais si la fiche est en état ``error``, une tentative a eu lieu puis a
          échoué : ses ressources sont restées côté Wazo, la reprise est
          légitime et le poste est réutilisé.

        Les plages appartiennent au contexte, donc au tenant : rien à
        configurer dans Odoo. Si le contexte n'en déclare **aucune**, il n'y a
        pas de règle à faire respecter et on laisse passer — sinon le module
        deviendrait inutilisable sur un PBX sans plages.
        """
        if existing is not None:
            # 1. Rattaché à un objet (autre type, ou le même) : refus net et
            #    précis. Les libellés sont ceux de la ressource, donc justes
            #    pour les deux modèles.
            for cle, libelle in OTHER_TYPE_LABELS.items():
                if existing.get(cle):
                    objet = existing.get(cle) or {}
                    nom = objet.get('label') or objet.get('name') or ''
                    raise UserError(
                        'Le poste %s appartient déjà à %s sur Wazo%s.'
                        % (self.extension, libelle,
                           ' (« %s »)' % nom if nom else ''))
            # 2. Reprise légitime ? Seulement après un échec constaté : dans
            #    l'état « nouveau », cette fiche n'a jamais été tentée, donc
            #    rien de ce qui existe côté Wazo ne peut venir d'elle.
            if self.wazo_state != 'error':
                occupant = self._extension_owner(client, existing)
                if occupant:
                    raise UserError(
                        'Le poste %s est déjà en service sur Wazo (utilisateur '
                        '« %s »). Choisissez un autre numéro, ou retirez ce '
                        'poste de son utilisateur actuel dans Wazo.'
                        % (self.extension, occupant))
                raise UserError(
                    'Le poste %s existe déjà sur Wazo sans être attribué '
                    '(ressource résiduelle). Supprimez-le dans Wazo, ou '
                    'choisissez un autre numéro — si c\'est la reprise d\'une '
                    'synchronisation interrompue, relancez par « Réessayer ».'
                    % self.extension)
            return

        libelle_type = RANGE_TYPE_LABELS.get(self._extension_type,
                                             self._extension_type)
        try:
            declarees = client.declared_ranges(context)
            if not any(declarees.values()):
                _logger.info(
                    'Aucune plage déclarée pour le contexte %s : poste %s '
                    'accepté sans contrôle de plage.',
                    context, self.extension)
                return

            # 1. Réservé à un autre type ? Ce contrôle passe **avant** celui de
            #    la plage attendue : un numéro réservé aux groupes n'est pas
            #    « hors plage », il est réservé — le message doit le dire.
            for type_, libelle in RANGE_TYPE_LABELS.items():
                if type_ == self._extension_type:
                    continue
                plages = declarees.get(type_) or []
                if in_ranges(self.extension, plages):
                    raise UserError(
                        'Le poste %s est réservé aux %s (plage %s du contexte '
                        '%s). Choisissez un autre numéro.'
                        % (self.extension, libelle,
                           ', '.join('%s-%s' % (p.get('start'), p.get('end'))
                                     for p in plages if p.get('start')),
                           context))

            # 2. Dans la plage de son propre type ?
            plages_type = declarees.get(self._extension_type) or []
            if not in_ranges(self.extension, plages_type):
                raise UserError(
                    "Le poste %s n'est dans aucune plage déclarée pour les %s "
                    'du contexte %s (plages : %s).'
                    % (self.extension, libelle_type, context,
                       ', '.join('%s-%s' % (p.get('start'), p.get('end'))
                                 for p in plages_type if p.get('start'))
                       or 'aucune'))

            # 3. Disponible ? La disponibilité est celle du PBX : toute
            #    extension existante y est prise, même non attribuée.
            if not in_ranges(self.extension,
                             client.ranges(context, self._extension_type)):
                raise UserError(
                    'Le poste %s est déjà attribué dans le contexte %s.'
                    % (self.extension, context))
        except WazoAPIError as error:
            # PBX muet sur les plages : on n'invente ni refus ni autorisation.
            # La synchro se poursuit et échouera d'elle-même s'il est
            # réellement indisponible.
            _logger.warning(
                'Plages illisibles pour le contexte %s (%s) : contrôle du '
                'poste %s ignoré.', context, error, self.extension)
