# Part of the mailcow_tenant Odoo module. See LICENSE for details.
from datetime import timedelta

from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError

from ..services.mailcow_client import MailcowAPIError
from ..services.mailcow_client import MailcowClient
from ..services.mailcow_client import en_nombre
from ..services.mailcow_client import refuser_la_disparition_totale


def _pourcentage(boite):
    """Part du quota consommee, ou rien si la boite est sans plafond.

    Calculee a partir des deux quotas locaux plutot que lue dans
    « percent_in_use » : ce dernier n'est rempli que par une synchronisation,
    si bien qu'une boite creee entre deux synchronisations paraitrait vide.

    Un quota a zero veut dire « sans limite » : rendre 0 % se lirait « vide »,
    soit exactement le contraire. Rien, plutot qu'un faux zero.
    """
    if not boite.quota_mb:
        return None
    return 100.0 * boite.quota_used_mb / boite.quota_mb


def _est_serree(boite):
    taux = _pourcentage(boite)
    return taux is not None and taux >= 80.0


def _taux_affiche(boite):
    taux = _pourcentage(boite)
    return None if taux is None else round(taux, 1)


def _derniere_connexion(boite):
    """La plus recente des trois, ou rien si le compte n'a jamais servi."""
    dates = [
        quand
        for quand in (boite.last_imap_login, boite.last_smtp_login, boite.last_pop3_login)
        if quand
    ]
    return max(dates) if dates else None


def _ligne_boite(boite):
    quand = _derniere_connexion(boite)
    return {
        "id": boite.id,
        "nom": boite.email,
        "domaine": boite.domain_id.name,
        "quota_mb": boite.quota_mb,
        "quota_utilise_mb": round(boite.quota_used_mb, 1),
        "pourcentage": _taux_affiche(boite),
        "messages": boite.messages,
        "active": boite.active,
        "synced": boite.synced,
        "derniere_connexion": quand.strftime("%Y-%m-%d") if quand else "",
    }


def _ligne_alias(un_alias):
    # L'adresse complete, telle que Mailcow la nomme : la partie locale seule
    # ne dirait rien a la lecture d'un tableau.
    return {
        "id": un_alias.id,
        "nom": "%s@%s" % (un_alias.alias_name, un_alias.domain_id.name),
        "domaine": un_alias.domain_id.name,
        "destinations": len(un_alias.address_ids),
        "catch_all": un_alias.is_catch_all,
        "active": un_alias.active,
        "synced": un_alias.synced,
    }


def _mesurer(domaines, boites, alias, jours_avant_dormance):
    """Les mesures et les alertes, pour une portee donnee.

    Appelee avec tout, elle decrit l'ensemble ; appelee avec les fiches d'un
    seul domaine, elle decrit ce domaine. Memes regles, autre portee : c'est
    ce qui garantit que le detail ne contredira pas la vue d'ensemble.

    Chaque alerte nomme ses fiches par identifiant plutot que par un critere
    comme « synced = faux » : un critere sans portee ouvrirait, depuis un
    domaine, les fiches de tous les autres.
    """
    seuil = fields.Datetime.now() - timedelta(days=jours_avant_dormance)
    actives = boites.filtered("active")
    serrees = actives.filtered(_est_serree)
    dormantes = actives.filtered(
        lambda boite: _derniere_connexion(boite) is None or _derniere_connexion(boite) < seuil
    )

    au_plafond = domaines.filtered(
        lambda domaine: domaine.mailboxes_max and domaine.mailboxes_used >= domaine.mailboxes_max
    )
    # Le meme seuil que la jauge et que les boites serrees : a 80 % la barre
    # est deja rouge, l'alerte ne doit pas attendre le refus de Mailcow. Ceux
    # qui sont au plafond ont leur propre alerte, plus grave.
    presque_pleins = (
        domaines.filtered(
            lambda domaine: domaine.mailboxes_max and domaine.occupation_boites >= 80.0
        )
        - au_plafond
    )
    sans_dkim = domaines.filtered(lambda domaine: domaine.active and not domaine.dkim_record)
    sans_destination = alias.filtered("active").filtered(
        lambda a: not a.is_catch_all and not a.address_ids
    )
    catch_all = alias.filtered("active").filtered("is_catch_all")
    sans_tls = actives.filtered(lambda boite: not boite.tls_enforce_in or not boite.tls_enforce_out)
    desactivees = boites.filtered(lambda boite: not boite.active)
    domaines_non_synchronises = domaines.filtered(lambda d: not d.synced)
    boites_non_synchronisees = boites.filtered(lambda b: not b.synced)
    alias_non_synchronises = alias.filtered(lambda a: not a.synced)

    # Chaque alerte porte le modele a ouvrir et le filtre a appliquer : le
    # composant n'a aucune condition a reecrire, il suit ce qu'on lui designe.
    # La regle vit donc au meme endroit que les autres regles du module, et se
    # teste sans navigateur.
    def alerte(cle, libelle, gravite, detail, modele, fiches):
        return {
            "cle": cle,
            "libelle": libelle,
            "gravite": gravite,
            "detail": detail,
            "modele": modele,
            "filtre": [("id", "in", fiches.ids)],
            "nombre": len(fiches),
        }

    return {
        "serrees": serrees,
        "dormantes": dormantes,
        "desactivees": desactivees,
        "alertes": [
            alerte(
                "domaines_au_plafond",
                "Domaines au plafond de boîtes",
                "danger",
                "Mailcow refusera la prochaine boîte créée.",
                "mailcow.domain",
                au_plafond,
            ),
            alerte(
                "domaines_presque_pleins",
                "Domaines à 80 % de leur plafond de boîtes",
                "attention",
                "Encore quelques créations, puis Mailcow refusera.",
                "mailcow.domain",
                presque_pleins,
            ),
            alerte(
                "boites_serrees",
                "Boîtes au-dessus de 80 % de leur quota",
                "attention",
                "La prochaine pièce jointe volumineuse passera mal.",
                "mailcow.mailbox",
                serrees,
            ),
            alerte(
                "boites_desactivees",
                "Boîtes désactivées",
                "attention",
                "Fermées sans être supprimées : l'adresse existe toujours.",
                "mailcow.mailbox",
                desactivees,
            ),
            alerte(
                "boites_dormantes",
                "Boîtes sans connexion depuis %d jours" % jours_avant_dormance,
                "attention",
                "Comptes ouverts, jamais utilisés : à fermer ou à assumer.",
                "mailcow.mailbox",
                dormantes,
            ),
            alerte(
                "tls_non_impose",
                "Boîtes sans TLS obligatoire",
                "danger",
                "Une connexion en clair reste possible sur ces comptes.",
                "mailcow.mailbox",
                sans_tls,
            ),
            alerte(
                "alias_sans_destination",
                "Alias sans destination",
                "attention",
                "Ces adresses reçoivent et ne transmettent nulle part.",
                "mailcow.alias",
                sans_destination,
            ),
            alerte(
                "catch_all",
                "Alias attrape-tout",
                "attention",
                "Tout ce qui est mal orthographié arrive quand même.",
                "mailcow.alias",
                catch_all,
            ),
            alerte(
                "dkim_absent",
                "Domaines sans clé DKIM enregistrée",
                "attention",
                "Sans DKIM, ces envois se font plus souvent refuser.",
                "mailcow.domain",
                sans_dkim,
            ),
            alerte(
                "domaines_non_synchronises",
                "Domaines non synchronisés",
                "information",
                "Fiches locales jamais confirmées par le serveur.",
                "mailcow.domain",
                domaines_non_synchronises,
            ),
            alerte(
                "boites_non_synchronisees",
                "Boîtes non synchronisées",
                "information",
                "Fiches locales jamais confirmées par le serveur.",
                "mailcow.mailbox",
                boites_non_synchronisees,
            ),
            alerte(
                "alias_non_synchronises",
                "Alias non synchronisés",
                "information",
                "Fiches locales jamais confirmées par le serveur.",
                "mailcow.alias",
                alias_non_synchronises,
            ),
        ],
    }


class MailcowDomain(models.Model):
    _name = "mailcow.domain"
    _inherit = ["mailcow.sync.mixin"]
    _description = "Mailcow: domaine"
    _order = "name"

    name = fields.Char(string="Domaine", required=True, index=True)
    description = fields.Char()
    quota_mb = fields.Integer(string="Quota (Mo)", default=0, help="0 = illimité")
    dkim_record = fields.Text(
        string="Enregistrement DKIM (DNS)",
        readonly=True,
        help="La ligne à publier dans le DNS du domaine. Jamais la clé privée.",
    )
    active = fields.Boolean(string="Actif", default=True)
    synced = fields.Boolean(string="Synchronisé avec Mailcow")
    mailboxes_max = fields.Integer(
        string="Boîtes maximum",
        default=0,
        help="0 = valeur du serveur. Au-delà de ce plafond, Mailcow refuse "
        "toute nouvelle boîte : une limite atteinte ne se voyait nulle "
        "part avant que la création échoue.",
    )
    aliases_max = fields.Integer(string="Alias maximum", default=0, help="0 = valeur du serveur.")
    mailboxes_used = fields.Integer(string="Boîtes utilisées", readonly=True)
    aliases_used = fields.Integer(string="Alias utilisés", readonly=True)
    # Au-dela de ce nombre de jours sans aucune connexion, un compte ouvert
    # est dit dormant : il occupe une place et une surface d'attaque sans servir.
    JOURS_AVANT_DORMANCE = 90

    occupation_boites = fields.Float(
        string="Occupation",
        compute="_compute_occupation",
        help="Part du plafond de boîtes déjà utilisée, en pourcentage.",
    )

    @api.depends("mailboxes_used", "mailboxes_max")
    def _compute_occupation(self):
        for domaine in self:
            domaine.occupation_boites = (
                100.0 * domaine.mailboxes_used / domaine.mailboxes_max
                if domaine.mailboxes_max
                else 0.0
            )

    mailboxes = fields.One2many("mailcow.mailbox", "domain_id", string="Boîtes mail")
    aliases = fields.One2many("mailcow.alias", "domain_id", string="Alias")

    _name_uniq = models.Constraint("unique(name)", "Ce domaine existe déjà.")

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
            "description": self.description or "",
            "active": "1" if self.active else "0",
        }
        if self.quota_mb > 0:
            attr["defquota"] = self.quota_mb
            attr["maxquota"] = self.quota_mb
            attr["quota"] = self.quota_mb
        # Les plafonds s'écrivent en NOMBRE DE BOÎTES et D'ALIAS — ni en Mio ni
        # en octets. Comme pour les quotas, un 0 local vaut « valeur du
        # serveur » : ne rien envoyer plutôt que d'imposer zéro.
        if self.mailboxes_max > 0:
            attr["mailboxes"] = self.mailboxes_max
        if self.aliases_max > 0:
            attr["aliases"] = self.aliases_max
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
        self._exiger("user")
        self.ensure_one()
        client = MailcowClient(self.env)
        reponse = client._request("GET", "/get/dkim/%s" % self.name, None)
        if isinstance(reponse, list) and reponse:
            reponse = reponse[0]
        if not isinstance(reponse, dict) or not reponse.get("dkim_txt"):
            raise UserError(
                self.env._(
                    "Le serveur n'a pas renvoyé de clé DKIM publique pour « %s ».", self.name
                )
            )
        selecteur = reponse.get("dkim_selector") or "dkim"
        valeur = reponse["dkim_txt"]
        if isinstance(valeur, list):
            valeur = "".join(valeur)
        self.dkim_record = '%s._domainkey.%s   TXT   "%s"' % (selecteur, self.name, valeur)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": "Mailcow",
                "sticky": False,
                "message": "L'enregistrement DKIM de %s est prêt." % self.name,
            },
        }

    def action_create_on_mailcow(self):
        """Crée le domaine sur Mailcow (ou le met à jour s'il existe déjà)."""
        self._exiger("user")
        for domain in self:
            client = MailcowClient(self.env)
            client._request("POST", "/add/domain", domain._payload())
            domain.write({"last_synced_on": fields.Datetime.now(), "synced": True})
            domain._journaliser("Domaine %s créé sur Mailcow." % domain.name)

    def action_update_on_mailcow(self):
        """Réécrit l'état local sur Mailcow."""
        self._exiger("user")
        for domain in self:
            client = MailcowClient(self.env)
            client._request(
                "POST",
                "/edit/domain",
                {
                    "items": [domain.name],
                    "attr": domain._attr_payload(),
                },
            )
            domain.write({"last_synced_on": fields.Datetime.now(), "synced": True})
            domain._journaliser("Mise à jour poussée vers Mailcow.")

    def action_delete_on_mailcow(self):
        """Supprime le domaine sur Mailcow, puis l'archive localement."""
        self._exiger("manager")
        for domain in self:
            client = MailcowClient(self.env)
            client._request("POST", "/delete/domain", {"domain": domain.name})
            domain.mailboxes.write({"synced": False})
            domain.aliases.write({"synced": False})
            domain.write({"synced": False, "active": False})
            domain._journaliser("Supprimé de Mailcow, et archivé ici.")

    def action_sync_from_mailcow(self):
        """Synchronise depuis cette fiche (voir action_sync_all_from_mailcow)."""
        self._exiger("sync")
        self.ensure_one()
        return self.env["mailcow.domain"].action_sync_all_from_mailcow()

    @api.model
    def action_sync_all_from_mailcow(self):
        """Aligner tout l'état local sur le serveur (bouton et menu).

        Le groupe Lecture et synchronisation lit les fiches sans pouvoir les
        écrire : la synchronisation écrit donc en sudo, APRÈS le contrôle, et
        n'appelle que des lectures (GET) du serveur.
        """
        self._exiger("sync")
        return self.sudo()._sync_all_from_mailcow()

    @api.model
    def donnees_tableau_de_bord(self):
        """Tout ce qu'affiche le tableau de bord, calculé une seule fois.

        Le calcul reste côté serveur. Compter les boîtes, jauger les quotas et
        repérer les domaines au bord de leur plafond doit obéir aux règles du
        module, pas à une deuxième version écrite en JavaScript qui
        divergerait au premier changement.
        """
        # Le tableau de bord compte tout, archivé compris : une limite fausserait
        # les totaux.
        domaines = self.with_context(active_test=False).search([])  # pylint: disable=no-search-all
        lignes = []
        for domaine in domaines:
            lignes.append(
                {
                    "id": domaine.id,
                    "nom": domaine.name,
                    "actif": domaine.active,
                    "synced": domaine.synced,
                    "boites_utilisees": domaine.mailboxes_used,
                    "boites_max": domaine.mailboxes_max,
                    "alias_utilises": domaine.aliases_used,
                    "alias_max": domaine.aliases_max,
                    # L'occupation est un champ calculé du modèle : une seule
                    # définition de « 8 sur 10 », ici. Sans plafond connu, rien
                    # plutôt qu'un faux zéro qui se lirait « vide ».
                    "occupation": (
                        round(domaine.occupation_boites, 1) if domaine.mailboxes_max else None
                    ),
                    "quota_mb": domaine.quota_mb,
                    "dkim": bool(domaine.dkim_record),
                    "derniere_synchro": (
                        domaine.last_synced_on.strftime("%Y-%m-%d %H:%M")
                        if domaine.last_synced_on
                        else ""
                    ),
                }
            )
        # Même raison : toutes les boîtes et tous les alias entrent dans les mesures.
        boites = self.env["mailcow.mailbox"].with_context(active_test=False).search([])  # pylint: disable=no-search-all
        alias = self.env["mailcow.alias"].with_context(active_test=False).search([])  # pylint: disable=no-search-all

        mesures = _mesurer(domaines, boites, alias, self.JOURS_AVANT_DORMANCE)
        alertes = mesures["alertes"]
        serrees = mesures["serrees"]
        dormantes = mesures["dormantes"]

        grosses = boites.sorted(lambda b: b.quota_used_mb, reverse=True)[:10]
        # Les comptes jamais utilisés d'abord : ce sont les cas les plus nets,
        # et les cacher derrière le plafond de dix serait les absoudre.
        recentes = sorted(
            dormantes,
            key=lambda b: (
                _derniere_connexion(b) is not None,
                _derniere_connexion(b) or fields.Datetime.now(),
            ),
        )[:10]
        allouees = [b.quota_mb for b in boites if b.quota_mb]

        # Les listes completes, avec l'identifiant de chaque fiche : c'est ce
        # qui permet de trier, de chercher, et d'ouvrir la bonne. Un instantane
        # suffit — le tableau se rafraichit en relisant cet appel, il
        # n'interroge pas Mailcow a chaque coup d'oeil.

        return {
            # get_str, pas get_param : c'est l'accesseur de cette version.
            "mailcow_url": self.env["ir.config_parameter"].get_str("mailcow.base_url", default=""),
            "domaines": lignes,
            "boites": [_ligne_boite(boite) for boite in boites],
            "alias": [_ligne_alias(un_alias) for un_alias in alias],
            "alertes": alertes,
            "grosses_boites": [
                {
                    "id": boite.id,
                    "nom": boite.email,
                    "pourcentage": _taux_affiche(boite),
                    "quota_utilise_mb": round(boite.quota_used_mb, 1),
                    "quota_mb": boite.quota_mb,
                    "messages": boite.messages,
                }
                for boite in grosses
            ],
            "dormantes": [
                {
                    "id": boite.id,
                    "nom": boite.email,
                    "derniere_connexion": (
                        _derniere_connexion(boite).strftime("%Y-%m-%d")
                        if _derniere_connexion(boite)
                        else "jamais"
                    ),
                }
                for boite in recentes
            ],
            "totaux": {
                "domaines": len(domaines),
                "boites": len(boites),
                "alias": len(alias),
                "messages": sum(boites.mapped("messages")),
                "quota_utilise_mb": round(sum(boites.mapped("quota_used_mb")), 1),
                "quota_alloue_mb": sum(allouees),
                "boites_sans_quota": len(boites) - len(allouees),
                "boites_serrees": len(serrees),
                "boites_dormantes": len(dormantes),
                "alertes": len([alerte for alerte in alertes if alerte["nombre"]]),
            },
        }

    def donnees_tableau_de_bord_domaine(self):
        """Tout ce qui concerne un domaine, et rien d'autre.

        Le tableau d'ensemble repond a « ou regarder » ; celui-ci repond a
        « qu'y a-t-il ici ». Il applique les memes regles — _mesurer les
        calcule sur ses seules fiches — si bien que le detail ne peut pas
        contredire l'ensemble. Et comme l'autre, il relit l'etat local d'Odoo,
        jamais Mailcow : ouvrir un domaine ne doit pas charger le serveur de
        courriel.
        """
        self.ensure_one()
        domaines = self
        boites = (
            self.env["mailcow.mailbox"]
            .with_context(active_test=False)
            .search([("domain_id", "=", self.id)])
        )
        alias = (
            self.env["mailcow.alias"]
            .with_context(active_test=False)
            .search([("domain_id", "=", self.id)])
        )
        mesures = _mesurer(domaines, boites, alias, self.JOURS_AVANT_DORMANCE)
        allouees = [boite.quota_mb for boite in boites if boite.quota_mb]

        return {
            "id": self.id,
            "nom": self.name,
            # get_str, pas get_param : c'est l'accesseur de cette version.
            "mailcow_url": self.env["ir.config_parameter"].get_str("mailcow.base_url", default=""),
            "identite": {
                "actif": self.active,
                "synced": self.synced,
                "description": self.description or "",
                "quota_mb": self.quota_mb,
                "boites_max": self.mailboxes_max,
                "alias_max": self.aliases_max,
                # Un plafond a zero veut dire « valeur du serveur » : afficher
                # « 0 sur 0 » se lirait « complet », soit le contraire.
                "plafond_connu": bool(self.mailboxes_max),
                "dkim": bool(self.dkim_record),
                "dkim_enregistrement": self.dkim_record or "",
                "derniere_synchro": (
                    self.last_synced_on.strftime("%Y-%m-%d %H:%M") if self.last_synced_on else ""
                ),
            },
            "chiffres": {
                "boites": len(boites),
                "boites_max": self.mailboxes_max,
                "occupation": (round(self.occupation_boites, 1) if self.mailboxes_max else None),
                "alias": len(alias),
                "alias_max": self.aliases_max,
                "messages": sum(boites.mapped("messages")),
                "espace_utilise_mb": round(sum(boites.mapped("quota_used_mb")), 1),
                "espace_alloue_mb": sum(allouees),
                "boites_sans_quota": len(boites) - len(allouees),
                "boites_serrees": len(mesures["serrees"]),
                "boites_dormantes": len(mesures["dormantes"]),
                "boites_desactivees": len(mesures["desactivees"]),
                "alertes": len([a for a in mesures["alertes"] if a["nombre"]]),
            },
            "boites": [_ligne_boite(boite) for boite in boites.sorted("email")],
            "alias": [_ligne_alias(un_alias) for un_alias in alias],
            "alertes": mesures["alertes"],
            "traffic": self._traffic(),
        }

    def _traffic(self):
        """File postfix, derniers messages et santé des services Mailcow.

        Une panne de mailcow ne doit pas rendre le tableau vide : chaque
        section est isolée, un échec affiche « non disponible ».
        """
        client = MailcowClient(self.env)
        queue = []
        try:
            response = client._request("GET", "/get/mailq/all", None)
            queue = response.get("data") if isinstance(response, dict) else response or []
        except (MailcowAPIError, OSError, UserError):
            queue = []
        messages = []
        try:
            response = client._request("GET", "/get/logs/rspamd-history", None)
            history = response.get("data") if isinstance(response, dict) else response or []
            for row in list(history)[:15]:
                messages.append(
                    {
                        "heure": str(row.get("time") or row.get("timestamp") or ""),
                        "expediteur": str(row.get("from") or row.get("sender") or ""),
                        "destinataire": str(row.get("rcpt") or row.get("to") or ""),
                        "score": row.get("score"),
                        "action": str(row.get("action") or ""),
                        "sujet": str(row.get("subject") or ""),
                    }
                )
        except (MailcowAPIError, OSError, UserError):
            messages = []
        services = []
        try:
            response = client._request("GET", "/get/status/containers", None)
            containers = response.get("data") if isinstance(response, dict) else response or []
            for container in containers:
                services.append(
                    {
                        "nom": container.get("name") or container.get("container") or "",
                        "etat": container.get("state") or container.get("status") or "",
                        "depuis": str(container.get("uptime") or ""),
                    }
                )
        except (MailcowAPIError, OSError, UserError):
            services = []
        return {
            "file_postfix": len(queue),
            "file_entrees": [
                {"destinataire": str(e.get("rcpt") or ""), "raison": str(e.get("reason") or "")}
                for e in queue[:10]
            ],
            "derniers_messages": messages,
            "services": services,
        }

    def action_ouvrir_tableau_de_bord_domaine(self):
        """Ouvrir le tableau de bord de ce domaine, depuis n'importe ou.

        Rendue comme action client plutot qu'en redirection : la fiche visee
        voyage avec l'action, ce qui rend le tableau atteignable d'un bouton de
        formulaire, d'une ligne de liste ou d'une URL — sans dependre de ce que
        la page regardait avant.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "mailcow_tenant.dashboard_domaine",
            "name": "Domaine %s" % self.name,
            "res_id": self.id,
            "params": {"resId": self.id},
        }

    @api.model
    def _sync_all_from_mailcow(self, dry_run=False):
        """Décrire, ou appliquer, l'état du serveur sur les fiches locales.

        S'appelle sans aucune fiche locale : c'est ainsi qu'on amorce une base
        vide, depuis l'en-tête d'une vue de liste ou le menu « Tout synchroniser ».
        """
        plan = []
        client = MailcowClient(self.env)
        response = client._request("GET", "/get/domain/all", None)
        entries = response.get("data") if isinstance(response, dict) else response
        refuser_la_disparition_totale(self.env, entries, "mailcow.domain", "domaine")
        remote_ids = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            # Mailcow nomme le domaine « domain_name » ; « domain » n'existe pas,
            # et s'y fier fait ignorer chaque entrée en silence.
            nom = entry.get("domain_name") or entry.get("domain")
            if not nom:
                continue
            remote_ids.add(nom)
            # Les fiches archivees comptent : une suppression archive la fiche
            # locale, et le domaine qui reapparait ensuite doit etre ravive, pas
            # recree — la contrainte d'unicite sur le nom ferait echouer toute
            # la synchronisation.
            domain = (
                self.env["mailcow.domain"]
                .with_context(active_test=False)
                .search([("name", "=", nom)], limit=1)
            )
            values = {
                "description": entry.get("description") or "",
                # Mailcow renvoie les quotas en octets.
                # Le quota peut arriver en texte : int() ferait lever la
                # synchronisation sur une valeur parfaitement valide.
                "quota_mb": int(en_nombre(entry.get("def_quota_for_mbox"))) // (1024 * 1024),
                # L'occupation et les plafonds du domaine : ce qui permet de
                # voir « 8 sur 10 » avant que la onzième boîte soit refusée.
                "mailboxes_used": int(en_nombre(entry.get("mboxes_in_domain"))),
                "aliases_used": int(en_nombre(entry.get("aliases_in_domain"))),
                "mailboxes_max": int(en_nombre(entry.get("max_num_mboxes_for_domain"))),
                "aliases_max": int(en_nombre(entry.get("max_num_aliases_for_domain"))),
                "active": entry.get("active") in (1, "1", True),
                "synced": True,
                "last_synced_on": fields.Datetime.now(),
            }
            if domain:
                self._poser(domain, values, plan, dry_run)
            else:
                self._creer("mailcow.domain", dict(values, name=nom), plan, dry_run, nom)
        # Les domaines locaux absents du serveur ne sont plus « synchronisés ».
        disparues = self.env["mailcow.domain"].search(
            [("name", "not in", list(remote_ids)), ("active", "=", True)]
        )
        if dry_run:
            for fiche in disparues:
                plan.append(
                    "%s « %s » : disparue du serveur" % (self._description, fiche._designation())
                )
        else:
            disparues.write({"synced": False})
        return plan
