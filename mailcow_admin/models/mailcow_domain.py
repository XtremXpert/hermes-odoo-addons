# Part of the mailcow_admin Odoo module. See LICENSE for details.
from datetime import timedelta

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError

from ..services.mailcow_client import MailcowClient
from ..services.mailcow_client import en_nombre
from ..services.mailcow_client import refuser_la_disparition_totale


class MailcowDomain(models.Model):
    _name = 'mailcow.domain'
    _inherit = ['mailcow.sync.mixin']
    _description = 'Mailcow: domaine'
    _order = 'name'

    name = fields.Char(string='Domaine', required=True, index=True)
    description = fields.Char(string='Description')
    quota_mb = fields.Integer(string='Quota (Mo)', default=0, help='0 = illimité')
    dkim_record = fields.Text(
        string='Enregistrement DKIM (DNS)',
        readonly=True,
        help="La ligne à publier dans le DNS du domaine. Jamais la clé privée.",
    )
    active = fields.Boolean(string='Actif', default=True)
    synced = fields.Boolean(string='Synchronisé avec Mailcow')
    mailboxes_max = fields.Integer(
        string='Boîtes maximum', default=0,
        help="0 = valeur du serveur. Au-delà de ce plafond, Mailcow refuse "
             "toute nouvelle boîte : une limite atteinte ne se voyait nulle "
             "part avant que la création échoue.",
    )
    aliases_max = fields.Integer(
        string='Alias maximum', default=0, help='0 = valeur du serveur.')
    mailboxes_used = fields.Integer(string='Boîtes utilisées', readonly=True)
    aliases_used = fields.Integer(string='Alias utilisés', readonly=True)
    # Au-dela de ce nombre de jours sans aucune connexion, un compte ouvert
    # est dit dormant : il occupe une place et une surface d'attaque sans servir.
    JOURS_AVANT_DORMANCE = 90

    occupation_boites = fields.Float(
        string='Occupation', compute='_compute_occupation',
        help='Part du plafond de boîtes déjà utilisée, en pourcentage.')

    @api.depends('mailboxes_used', 'mailboxes_max')
    def _compute_occupation(self):
        for domaine in self:
            domaine.occupation_boites = (
                100.0 * domaine.mailboxes_used / domaine.mailboxes_max
                if domaine.mailboxes_max else 0.0)

    mailboxes = fields.One2many('mailcow.mailbox', 'domain_id', string='Boîtes mail')
    aliases = fields.One2many('mailcow.alias', 'domain_id', string='Alias')

    _name_uniq = models.Constraint(
        'unique(name)', 'Ce domaine existe déjà.')

    # --- Actions Mailcow --------------------------------------------------

    def _attr_payload(self):
        """Les attributs modifiables d'un domaine : le « attr » d'une édition.

        Mailcow attend {"items": [domaine], "attr": {...}} et ignore un corps
        plat en répondant « success ». Le nom est l'identité, pas un attribut.

        Les quotas s'écrivent en MIO sous les noms « defquota », « maxquota »
        et « quota » — les mêmes pour /add/domain et pour /edit/domain, comme
        le montre l'exemple de l'API (« defquota: 3072 », « maxquota: 10240 »,
        qui sont aussi les valeurs par défaut du serveur). « def_quota_for_mbox »
        et « max_quota_for_domain » sont les noms de la RELECTURE : mesuré sur
        le serveur, /edit/domain les recopie dans son journal, répond
        « success », et n'applique rien.

        Un quota local à 0 vaut « illimité » : on n'envoie rien plutôt que
        d'écraser la politique de quotas du serveur.
        """
        self.ensure_one()
        attr = {
            'description': self.description or '',
            'active': '1' if self.active else '0',
        }
        if self.quota_mb > 0:
            attr['defquota'] = self.quota_mb
            attr['maxquota'] = self.quota_mb
            attr['quota'] = self.quota_mb
        # Les plafonds s'écrivent en NOMBRE DE BOÎTES et D'ALIAS — ni en Mio ni
        # en octets. Comme pour les quotas, un 0 local vaut « valeur du
        # serveur » : ne rien envoyer plutôt que d'imposer zéro.
        if self.mailboxes_max > 0:
            attr['mailboxes'] = self.mailboxes_max
        if self.aliases_max > 0:
            attr['aliases'] = self.aliases_max
        return attr

    def _payload(self):
        """La charge de création : le nom, plus les attributs modifiables.

        Les deux routes d'écriture, /add/domain et /edit/domain, partagent le
        vocabulaire décrit dans _attr_payload : les quotas s'y écrivent en MIO.
        """
        self.ensure_one()
        return dict(self._attr_payload(), domain=self.name)

    def action_fetch_dkim(self):
        """Relit la clé DKIM PUBLIQUE du domaine, à publier dans le DNS.

        Mailcow renvoie aussi la clé privée dans la même réponse : elle n'est
        jamais lue ici, et donc jamais rangée dans Odoo.
        """
        self.ensure_one()
        client = MailcowClient(self.env)
        reponse = client._request('GET', '/get/dkim/%s' % self.name, None)
        if isinstance(reponse, list) and reponse:
            reponse = reponse[0]
        if not isinstance(reponse, dict) or not reponse.get('dkim_txt'):
            raise UserError(
                "Le serveur n'a pas renvoyé de clé DKIM publique pour « %s »."
                % self.name
            )
        selecteur = reponse.get('dkim_selector') or 'dkim'
        valeur = reponse['dkim_txt']
        if isinstance(valeur, list):
            valeur = ''.join(valeur)
        self.dkim_record = '%s._domainkey.%s   TXT   "%s"' % (
            selecteur, self.name, valeur)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': 'Mailcow',
                'sticky': False,
                'message': "L'enregistrement DKIM de %s est prêt." % self.name,
            },
        }

    def action_create_on_mailcow(self):
        """Crée le domaine sur Mailcow (ou le met à jour s'il existe déjà)."""
        for domain in self:
            client = MailcowClient(self.env)
            client._request('POST', '/add/domain', domain._payload())
            domain.write({'last_synced_on': fields.Datetime.now(), 'synced': True})
            domain._journaliser('Domaine %s créé sur Mailcow.' % domain.name)

    def action_update_on_mailcow(self):
        """Réécrit l'état local sur Mailcow."""
        for domain in self:
            client = MailcowClient(self.env)
            client._request('POST', '/edit/domain', {
                'items': [domain.name],
                'attr': domain._attr_payload(),
            })
            domain.write({'last_synced_on': fields.Datetime.now(), 'synced': True})
            domain._journaliser('Mise à jour poussée vers Mailcow.')

    def action_delete_on_mailcow(self):
        """Supprime le domaine sur Mailcow, puis l'archive localement."""
        for domain in self:
            client = MailcowClient(self.env)
            client._request('POST', '/delete/domain', {'domain': domain.name})
            domain.mailboxes.write({'synced': False})
            domain.aliases.write({'synced': False})
            domain.write({'synced': False, 'active': False})
            domain._journaliser('Supprimé de Mailcow, et archivé ici.')

    def action_sync_from_mailcow(self):
        """Synchronise depuis cette fiche (voir action_sync_all_from_mailcow)."""
        self.ensure_one()
        return self.env['mailcow.domain'].action_sync_all_from_mailcow()

    @api.model
    def action_sync_all_from_mailcow(self):
        """Aligner tout l'état local sur le serveur (bouton et menu)."""
        return self._sync_all_from_mailcow()

    @api.model
    def donnees_tableau_de_bord(self):
        """Tout ce qu'affiche le tableau de bord, calculé une seule fois.

        Le calcul reste côté serveur. Compter les boîtes, jauger les quotas et
        repérer les domaines au bord de leur plafond doit obéir aux règles du
        module, pas à une deuxième version écrite en JavaScript qui
        divergerait au premier changement.
        """
        domaines = self.with_context(active_test=False).search([])
        lignes = []
        for domaine in domaines:
            lignes.append({
                'id': domaine.id,
                'nom': domaine.name,
                'actif': domaine.active,
                'synced': domaine.synced,
                'boites_utilisees': domaine.mailboxes_used,
                'boites_max': domaine.mailboxes_max,
                'alias_utilises': domaine.aliases_used,
                'alias_max': domaine.aliases_max,
                # L'occupation est un champ calculé du modèle : une seule
                # définition de « 8 sur 10 », ici.
                'occupation': round(domaine.occupation_boites, 1),
                'quota_mb': domaine.quota_mb,
                'dkim': bool(domaine.dkim_record),
                'derniere_synchro': (
                    domaine.last_synced_on.strftime('%Y-%m-%d %H:%M')
                    if domaine.last_synced_on else ''),
            })
        boites = self.env['mailcow.mailbox'].with_context(active_test=False).search([])
        alias = self.env['mailcow.alias'].with_context(active_test=False).search([])

        def pourcentage(boite):
            """Part du quota consommée, ou rien si la boîte est sans plafond.

            Calculée à partir des deux quotas locaux plutôt que lue dans
            « percent_in_use » : ce dernier n'est rempli que par une
            synchronisation, si bien qu'une boîte créée entre deux
            synchronisations paraîtrait vide.

            Un quota à zéro veut dire « sans limite » : rendre 0 % se lirait
            « vide », soit exactement le contraire. Rien, plutôt qu'un faux zéro.
            """
            if not boite.quota_mb:
                return None
            return 100.0 * boite.quota_used_mb / boite.quota_mb

        def est_serree(boite):
            taux = pourcentage(boite)
            return taux is not None and taux >= 80.0

        def taux_affiche(boite):
            taux = pourcentage(boite)
            return None if taux is None else round(taux, 1)

        def derniere_connexion(boite):
            """La plus récente des trois, ou rien si le compte n'a jamais servi."""
            dates = [
                quand for quand in (
                    boite.last_imap_login, boite.last_smtp_login, boite.last_pop3_login)
                if quand
            ]
            return max(dates) if dates else None

        seuil = fields.Datetime.now() - timedelta(days=self.JOURS_AVANT_DORMANCE)
        actives = boites.filtered('active')
        serrees = actives.filtered(est_serree)
        dormantes = actives.filtered(
            lambda boite: derniere_connexion(boite) is None
            or derniere_connexion(boite) < seuil)

        au_plafond = domaines.filtered(
            lambda domaine: domaine.mailboxes_max
            and domaine.mailboxes_used >= domaine.mailboxes_max)
        sans_dkim = domaines.filtered(lambda domaine: domaine.active and not domaine.dkim_record)
        sans_destination = alias.filtered('active').filtered(
            lambda a: not a.is_catch_all and not a.address_ids)
        catch_all = alias.filtered('active').filtered('is_catch_all')
        sans_tls = actives.filtered(
            lambda boite: not boite.tls_enforce_in or not boite.tls_enforce_out)
        desactivees = boites.filtered(lambda boite: not boite.active)

        # Chaque alerte porte le modèle à ouvrir et le filtre à appliquer : le
        # composant n'a aucune condition à réécrire, il suit ce qu'on lui désigne.
        # La règle vit donc au même endroit que les autres règles du module, et
        # se teste sans navigateur.
        alertes = [
            {
                'cle': 'domaines_au_plafond',
                'libelle': 'Domaines au plafond de boîtes',
                'gravite': 'danger',
                'detail': 'Mailcow refusera la prochaine boîte créée.',
                'modele': 'mailcow.domain',
                'filtre': [('id', 'in', au_plafond.ids)],
                'nombre': len(au_plafond),
            },
            {
                'cle': 'boites_serrees',
                'libelle': 'Boîtes au-dessus de 80 % de leur quota',
                'gravite': 'attention',
                'detail': 'La prochaine pièce jointe volumineuse passera mal.',
                'modele': 'mailcow.mailbox',
                'filtre': [('id', 'in', serrees.ids)],
                'nombre': len(serrees),
            },
            {
                'cle': 'boites_desactivees',
                'libelle': 'Boîtes désactivées',
                'gravite': 'attention',
                'detail': "Fermées sans être supprimées : l'adresse existe toujours.",
                'modele': 'mailcow.mailbox',
                'filtre': [('id', 'in', desactivees.ids)],
                'nombre': len(desactivees),
            },
            {
                'cle': 'boites_dormantes',
                'libelle': 'Boîtes sans connexion depuis %d jours' % self.JOURS_AVANT_DORMANCE,
                'gravite': 'attention',
                'detail': 'Comptes ouverts, jamais utilisés : à fermer ou à assumer.',
                'modele': 'mailcow.mailbox',
                'filtre': [('id', 'in', dormantes.ids)],
                'nombre': len(dormantes),
            },
            {
                'cle': 'tls_non_impose',
                'libelle': 'Boîtes sans TLS obligatoire',
                'gravite': 'danger',
                'detail': 'Une connexion en clair reste possible sur ces comptes.',
                'modele': 'mailcow.mailbox',
                'filtre': [('id', 'in', sans_tls.ids)],
                'nombre': len(sans_tls),
            },
            {
                'cle': 'alias_sans_destination',
                'libelle': 'Alias sans destination',
                'gravite': 'attention',
                'detail': 'Ces adresses reçoivent et ne transmettent nulle part.',
                'modele': 'mailcow.alias',
                'filtre': [('id', 'in', sans_destination.ids)],
                'nombre': len(sans_destination),
            },
            {
                'cle': 'catch_all',
                'libelle': 'Alias attrape-tout',
                'gravite': 'attention',
                'detail': 'Tout ce qui est mal orthographié arrive quand même.',
                'modele': 'mailcow.alias',
                'filtre': [('id', 'in', catch_all.ids)],
                'nombre': len(catch_all),
            },
            {
                'cle': 'dkim_absent',
                'libelle': 'Domaines sans clé DKIM enregistrée',
                'gravite': 'attention',
                'detail': 'Sans DKIM, ces envois se font plus souvent refuser.',
                'modele': 'mailcow.domain',
                'filtre': [('id', 'in', sans_dkim.ids)],
                'nombre': len(sans_dkim),
            },
            {
                'cle': 'domaines_non_synchronises',
                'libelle': 'Domaines non synchronisés',
                'gravite': 'information',
                'detail': 'Fiches locales jamais confirmées par le serveur.',
                'modele': 'mailcow.domain',
                'filtre': [('synced', '=', False)],
                'nombre': len(domaines.filtered(lambda d: not d.synced)),
            },
            {
                'cle': 'boites_non_synchronisees',
                'libelle': 'Boîtes non synchronisées',
                'gravite': 'information',
                'detail': 'Fiches locales jamais confirmées par le serveur.',
                'modele': 'mailcow.mailbox',
                'filtre': [('synced', '=', False)],
                'nombre': len(boites.filtered(lambda b: not b.synced)),
            },
            {
                'cle': 'alias_non_synchronises',
                'libelle': 'Alias non synchronisés',
                'gravite': 'information',
                'detail': 'Fiches locales jamais confirmées par le serveur.',
                'modele': 'mailcow.alias',
                'filtre': [('synced', '=', False)],
                'nombre': len(alias.filtered(lambda a: not a.synced)),
            },
        ]

        grosses = boites.sorted(lambda b: b.quota_used_mb, reverse=True)[:10]
        # Les comptes jamais utilisés d'abord : ce sont les cas les plus nets,
        # et les cacher derrière le plafond de dix serait les absoudre.
        recentes = sorted(
            dormantes,
            key=lambda b: (derniere_connexion(b) is not None,
                           derniere_connexion(b) or fields.Datetime.now()))[:10]
        allouees = [b.quota_mb for b in boites if b.quota_mb]
        return {
            'domaines': lignes,
            'alertes': alertes,
            'grosses_boites': [{
                'id': boite.id,
                'nom': boite.email,
                'pourcentage': taux_affiche(boite),
                'quota_utilise_mb': round(boite.quota_used_mb, 1),
                'quota_mb': boite.quota_mb,
                'messages': boite.messages,
            } for boite in grosses],
            'dormantes': [{
                'id': boite.id,
                'nom': boite.email,
                'derniere_connexion': (
                    derniere_connexion(boite).strftime('%Y-%m-%d')
                    if derniere_connexion(boite) else 'jamais'),
            } for boite in recentes],
            'totaux': {
                'domaines': len(domaines),
                'boites': len(boites),
                'alias': len(alias),
                'messages': sum(boites.mapped('messages')),
                'quota_utilise_mb': round(sum(boites.mapped('quota_used_mb')), 1),
                'quota_alloue_mb': sum(allouees),
                'boites_sans_quota': len(boites) - len(allouees),
                'boites_serrees': len(serrees),
                'boites_dormantes': len(dormantes),
                'alertes': len([alerte for alerte in alertes if alerte['nombre']]),
            },
        }

    @api.model
    def _sync_all_from_mailcow(self, dry_run=False):
        """Décrire, ou appliquer, l'état du serveur sur les fiches locales.

        S'appelle sans aucune fiche locale : c'est ainsi qu'on amorce une base
        vide, depuis l'en-tête d'une vue de liste ou le menu « Tout synchroniser ».
        """
        plan = []
        client = MailcowClient(self.env)
        response = client._request('GET', '/get/domain/all', None)
        entries = response.get('data') if isinstance(response, dict) else response
        refuser_la_disparition_totale(
            self.env, entries, 'mailcow.domain', 'domaine')
        remote_ids = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            # Mailcow nomme le domaine « domain_name » ; « domain » n'existe pas,
            # et s'y fier fait ignorer chaque entrée en silence.
            nom = entry.get('domain_name') or entry.get('domain')
            if not nom:
                continue
            remote_ids.add(nom)
            # Les fiches archivees comptent : une suppression archive la fiche
            # locale, et le domaine qui reapparait ensuite doit etre ravive, pas
            # recree — la contrainte d'unicite sur le nom ferait echouer toute
            # la synchronisation.
            domain = self.env['mailcow.domain'].with_context(
                active_test=False).search([('name', '=', nom)], limit=1)
            values = {
                'description': entry.get('description') or '',
                # Mailcow renvoie les quotas en octets.
                # Le quota peut arriver en texte : int() ferait lever la
                # synchronisation sur une valeur parfaitement valide.
                'quota_mb': int(en_nombre(entry.get('def_quota_for_mbox'))) // (1024 * 1024),
                # L'occupation et les plafonds du domaine : ce qui permet de
                # voir « 8 sur 10 » avant que la onzième boîte soit refusée.
                'mailboxes_used': int(en_nombre(entry.get('mboxes_in_domain'))),
                'aliases_used': int(en_nombre(entry.get('aliases_in_domain'))),
                'mailboxes_max': int(en_nombre(entry.get('max_num_mboxes_for_domain'))),
                'aliases_max': int(en_nombre(entry.get('max_num_aliases_for_domain'))),
                'active': entry.get('active') in (1, '1', True),
                'synced': True,
                'last_synced_on': fields.Datetime.now(),
            }
            if domain:
                self._poser(domain, values, plan, dry_run)
            else:
                self._creer('mailcow.domain', dict(values, name=nom),
                            plan, dry_run, nom)
        # Les domaines locaux absents du serveur ne sont plus « synchronisés ».
        disparues = self.env['mailcow.domain'].search(
            [('name', 'not in', list(remote_ids)), ('active', '=', True)])
        if dry_run:
            for fiche in disparues:
                plan.append('%s « %s » : disparue du serveur'
                            % (self._description, fiche._designation()))
        else:
            disparues.write({'synced': False})
        return plan
