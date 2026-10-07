# Part of the mailcow_admin Odoo module. See LICENSE for details.
from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

from ..services.mailcow_client import MailcowClient
from ..services.mailcow_client import refuser_la_disparition_totale


class MailcowAlias(models.Model):
    _name = "mailcow.alias"
    _inherit = ["mailcow.sync.mixin"]
    _description = "Mailcow: alias"
    _order = "domain_id, alias_name"

    alias_name = fields.Char(string="Nom d'alias")
    domain_id = fields.Many2one(
        "mailcow.domain",
        string="Domaine",
        required=True,
        ondelete="cascade",
        index=True,
    )
    address_ids = fields.Many2many("mailcow.email_address", string="Adresses de destination")
    active = fields.Boolean(string="Actif", default=True)
    description = fields.Char()
    synced = fields.Boolean(string="Synchronisé avec Mailcow")
    mailcow_id = fields.Char(string="ID Mailcow", readonly=True)
    is_catch_all = fields.Boolean(
        string="Fourre-tout",
        help="Alias qui reçoit tout le courrier du domaine : son adresse est "
        "« @domaine », sans partie locale.",
    )

    _alias_domain_uniq = models.Constraint(
        "unique(alias_name, domain_id)", "Cet alias existe déjà sur ce domaine."
    )

    @api.depends("alias_name", "domain_id", "domain_id.name", "is_catch_all")
    def _compute_display_name(self):
        for alias in self:
            if alias.is_catch_all or not alias.alias_name:
                alias.display_name = "@%s" % (alias.domain_id.name or "")
            else:
                alias.display_name = "%s@%s" % (alias.alias_name, alias.domain_id.name or "")

    @api.constrains("alias_name", "is_catch_all")
    def _check_catch_all_name(self):
        for alias in self:
            if bool(alias.is_catch_all) != (not alias.alias_name):
                raise ValidationError(
                    self.env._(
                        "Un alias fourre-tout n'a pas de partie locale (« @domaine ») "
                        "et un alias ordinaire en a une : cochez « Fourre-tout » pour "
                        "un alias sans nom."
                    )
                )

    # --- Actions Mailcow --------------------------------------------------

    def _payload(self):
        self.ensure_one()
        return {
            # Mailcow attend l'adresse complète de l'alias (sans partie locale
            # pour un fourre-tout) et ses destinations en une chaîne séparée
            # par des virgules.
            "address": "%s@%s" % (self.alias_name or "", self.domain_id.name),
            "goto": ",".join(self.address_ids.mapped("address")),
            "active": "1" if self.active else "0",
            "description": self.description or "",
        }

    def _ensure_addresses(self):
        self.ensure_one()
        if not self.address_ids:
            raise UserError(
                self.env._(
                    "Renseignez au moins une adresse de destination pour l'alias « %s » "
                    "avant de le créer sur Mailcow.",
                    self.alias_name,
                )
            )

    def action_create_on_mailcow(self):
        """Crée l'alias sur Mailcow, puis range son identifiant.

        La réponse de création ne le donne pas : on le relit, sans quoi la
        première modification devrait aller le chercher elle-même.
        """
        for alias in self:
            alias._ensure_addresses()
            client = MailcowClient(self.env)
            client._request("POST", "/add/alias", alias._payload())
            alias.write({"last_synced_on": fields.Datetime.now(), "synced": True})
            alias._journaliser(
                "Alias %s créé sur Mailcow." % (alias.alias_name or "@%s" % alias.domain_id.name)
            )
            identifiant = alias._remote_id()
            if identifiant:
                alias.write({"mailcow_id": str(identifiant)})

    def _attr_payload(self):
        """Les attributs modifiables d'un alias : le « attr » d'une édition.

        L'identifiant Mailcow est l'identité (il va dans « items ») ; un corps
        plat, ou l'adresse seule, ne modifient rien malgré un « success ».
        """
        self.ensure_one()
        return {
            "goto": ",".join(self.address_ids.mapped("address")),
            "active": "1" if self.active else "0",
            "description": self.description or "",
        }

    def _remote_id(self):
        """L'identifiant de l'alias sur le serveur (il s'édite par identifiant)."""
        self.ensure_one()
        attendue = "%s@%s" % (self.alias_name or "", self.domain_id.name)
        reponse = MailcowClient(self.env)._request("GET", "/get/alias/all", None)
        entrees = reponse.get("data") if isinstance(reponse, dict) else reponse
        for entree in entrees:
            if entree.get("address") == attendue and entree.get("id") is not None:
                return str(entree["id"])
        return self.mailcow_id or None

    def action_update_on_mailcow(self):
        """Réécrit l'état local sur Mailcow."""
        for alias in self:
            alias._ensure_addresses()
            identifiant = alias.mailcow_id or alias._remote_id()
            if not identifiant:
                raise UserError(
                    self.env._(
                        "Alias « %s » introuvable sur Mailcow : synchronisez d'abord.",
                        alias.display_name,
                    )
                )
            client = MailcowClient(self.env)
            client._request(
                "POST",
                "/edit/alias",
                {
                    "items": [str(identifiant)],
                    "attr": alias._attr_payload(),
                },
            )
            alias.write(
                {
                    "last_synced_on": fields.Datetime.now(),
                    "synced": True,
                    "mailcow_id": str(identifiant),
                }
            )
            alias._journaliser("Mise à jour poussée vers Mailcow.")

    def action_delete_on_mailcow(self):
        """Supprime l'alias sur Mailcow, puis l'archive localement."""
        for alias in self:
            client = MailcowClient(self.env)
            client._request(
                "POST",
                "/delete/alias",
                {
                    "address": "%s@%s" % (alias.alias_name or "", alias.domain_id.name),
                },
            )
            alias.write({"synced": False, "active": False})
            alias._journaliser("Supprimé de Mailcow, et archivé ici.")

    def _address_records(self, addresses):
        """Renvoie (en créant au besoin) les enregistrements d'adresse."""
        records = self.env["mailcow.email_address"]
        for address in addresses:
            record = self.env["mailcow.email_address"].search([("address", "=", address)], limit=1)
            if not record:
                record = self.env["mailcow.email_address"].create({"address": address})
            records |= record
        return records

    def action_sync_from_mailcow(self):
        """Synchronise depuis cette fiche (voir action_sync_all_from_mailcow)."""
        self.ensure_one()
        return self.env["mailcow.alias"].action_sync_all_from_mailcow()

    @api.model
    def action_sync_all_from_mailcow(self):
        """Aligner tout l'état local sur le serveur (bouton et menu)."""
        return self._sync_all_from_mailcow()

    @api.model
    def _sync_all_from_mailcow(self, dry_run=False):
        """Décrire, ou appliquer, l'état du serveur sur les fiches locales.

        S'appelle sans aucune fiche locale : c'est ainsi qu'on amorce une base
        vide, depuis l'en-tête d'une vue de liste ou le menu « Tout synchroniser ».
        """
        plan = []
        client = MailcowClient(self.env)
        response = client._request("GET", "/get/alias/all", None)
        entries = response.get("data") if isinstance(response, dict) else response
        refuser_la_disparition_totale(self.env, entries, "mailcow.alias", "alias")
        remote_keys = set()
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("domain"):
                continue
            # Mailcow met l'adresse de l'alias dans « address » et ses
            # destinations dans « goto » ; « alias_name » n'existe pas, et s'y
            # fier fait ignorer chaque entrée en silence.
            adresse = entry.get("address") or ""
            if not adresse:
                continue
            # Un fourre-tout n'a pas de partie locale : son adresse est
            # « @domaine », et il doit être importé comme tel.
            alias_name = adresse.split("@")[0]
            est_fourre_tout = bool(entry.get("is_catch_all")) or not alias_name
            destinations = entry.get("goto")
            if isinstance(destinations, str):
                destinations = [item.strip() for item in destinations.split(",") if item.strip()]
            elif not isinstance(destinations, list):
                destinations = []
            domain = self.env["mailcow.domain"].search([("name", "=", entry["domain"])], limit=1)
            if not domain:  # domaine vu côté serveur, créé à la volée
                if dry_run:
                    plan.append(
                        "%s « %s » : domaine à créer" % (self._description, entry["domain"])
                    )
                    continue
                domain = self.env["mailcow.domain"].create({"name": entry["domain"]})
            remote_keys.add((alias_name, domain.id))
            alias = self.env["mailcow.alias"].search(
                [("alias_name", "=", alias_name), ("domain_id", "=", domain.id)],
                limit=1,
            )
            values = {
                "description": entry.get("description") or "",
                "active": entry.get("active") in (1, "1", True),
                "synced": True,
                "last_synced_on": fields.Datetime.now(),
                "is_catch_all": est_fourre_tout,
            }
            if not dry_run:
                # En aperçu, on ne crée même pas les adresses de destination :
                # décrire ne doit rien laisser derrière soi.
                values["address_ids"] = [(6, 0, self._address_records(destinations).ids)]
            if entry.get("id") is not None:
                values["mailcow_id"] = str(entry["id"])
            etiquette = "%s@%s" % (alias_name, entry["domain"])
            if alias:
                self._poser(alias, values, plan, dry_run)
            else:
                self._creer(
                    "mailcow.alias",
                    dict(values, alias_name=alias_name, domain_id=domain.id),
                    plan,
                    dry_run,
                    etiquette,
                )
        # Les alias locaux absents du serveur ne sont plus « synchronisés ».
        disparues = (
            self.env["mailcow.alias"]
            .search([("active", "=", True)])
            .filtered(
                # Odoo stocke False dans un Char vide : comparer False à ''
                # ferait passer le fourre-tout pour absent du serveur.
                lambda a: ((a.alias_name or ""), a.domain_id.id) not in remote_keys
            )
        )
        if dry_run:
            for fiche in disparues:
                plan.append(
                    "%s « %s » : disparue du serveur" % (self._description, fiche._designation())
                )
        else:
            disparues.write({"synced": False})
        return plan
