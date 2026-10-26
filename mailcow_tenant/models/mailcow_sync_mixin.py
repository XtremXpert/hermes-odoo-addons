# Part of the mailcow_tenant Odoo module. See LICENSE for details.
from odoo import api
from odoo import fields
from odoo import models
from odoo.exceptions import AccessError


class MailcowSyncMixin(models.AbstractModel):
    """Ce que les trois objets Mailcow partagent.

    La date de dernière synchronisation est ce qui distingue une fiche
    DISPARUE du serveur (on l'y avait vue, Mailcow ne la liste plus) d'une
    fiche JAMAIS POUSSÉE (elle n'a jamais existé que dans Odoo). Sans elle,
    les deux se ressemblent — et on ne nettoie pas de la même façon.
    """

    _name = "mailcow.sync.mixin"
    _inherit = ["mail.thread"]
    _description = "Mailcow : suivi de synchronisation"

    last_synced_on = fields.Datetime(string="Dernière synchronisation", readonly=True)

    @api.model
    def _exiger(self, groupe):
        """Refuser l'appel à qui n'a pas le groupe, AVANT tout appel au serveur.

        Une méthode publique s'appelle par RPC : l'attribut « groups » d'un
        bouton ne protège que l'écran. Lecture et synchronisation : lire et
        aligner Odoo sur le serveur, sans jamais écrire sur Mailcow (le groupe
        des agents) ; utilisateur : créer et mettre à jour ; gestionnaire :
        supprimer, changer un mot de passe, et tout le reste.
        """
        if self.env.su or self.env.user.has_group("mailcow_tenant.group_mailcow_" + groupe):
            return
        nom = {
            "manager": "Gestionnaire",
            "user": "Utilisateur",
            "sync": "Lecture et synchronisation",
        }[groupe]
        raise AccessError(self.env._("Action Mailcow réservée au groupe %s.", nom))

    def _journaliser(self, corps):
        """Noter dans le fil de la fiche ce qui vient d'être fait sur Mailcow.

        Le fil porte l'auteur et l'heure : on n'y répète que le geste.
        """
        for fiche in self:
            fiche.message_post(body=corps, subtype_xmlid="mail.mt_note")

    def _designation(self):
        """Comment nommer cette fiche dans un compte rendu.

        Le nom affiché d'une boîte est son nom complet, parfois vide : il
        vaut mieux l'adresse, qui ne l'est jamais.
        """
        self.ensure_one()
        return self.display_name

    @api.model
    def action_preview_sync_from_mailcow(self):
        """Ouvrir l'aperçu de ce qu'une synchronisation changerait.

        Rien n'est écrit, ni dans Odoo ni sur le serveur : la lecture seule du
        serveur suffit à décrire le plan.
        """
        self._exiger("sync")
        plan = self._sync_all_from_mailcow(dry_run=True)
        apercu = self.env["mailcow.sync.preview"].create(
            {
                "model_name": self._description,
                "plan": "\n".join(plan)
                or "Rien à changer : l'état local est déjà celui du serveur.",
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Aperçu de la synchronisation",
            "res_model": "mailcow.sync.preview",
            "res_id": apercu.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_preview_sync(self):
        """L'aperçu, appelé depuis une fiche.

        L'API JSON-2 refuse des identifiants sur une méthode @api.model, et
        l'outil Odoo des agents en passe toujours : une fiche quelconque du
        même objet sert de point d'entrée. Les droits sont ceux de l'aperçu.
        """
        return self.env[self._name].action_preview_sync_from_mailcow()

    @api.model
    def _domaines_autorises(self):
        """Le périmètre des domaines du tenant, ou None si le serveur entier.

        ``mailcow.allowed_domains`` porte une liste séparée par des virgules :
        ``diverse-cite.com`` pour un tenant, vide chez l'opérateur — qui voit
        tout le serveur. Une instance tenant ne doit jamais rapatrier les
        domaines des autres.
        """
        brut = self.env["ir.config_parameter"].sudo().get_str("mailcow.allowed_domains", "")
        autorises = {d.strip() for d in brut.split(",") if d.strip()}
        return autorises or None

    @api.model
    def _ecarts(self, fiche, valeurs):
        """Les champs dont le serveur s'écarte de la fiche locale."""
        ecarts = []
        for champ, valeur in valeurs.items():
            if champ in ("synced", "last_synced_on"):
                continue
            actuel = fiche[champ]
            if isinstance(fiche._fields[champ], fields.Datetime):
                # Ni la date vide côté serveur ni la date absente côté Odoo ne
                # valent un changement : les deux se ramènent à None.
                attendu = fields.Datetime.to_datetime(valeur) if valeur else None
                if attendu != (actuel or None):
                    ecarts.append(champ)
            elif (actuel or "") != (valeur or ""):
                # Odoo range False là où le serveur envoie une chaîne vide :
                # les comparer tels quels annoncerait un changement perpétuel.
                ecarts.append(champ)
        return ecarts

    @api.model
    def _poser(self, fiche, valeurs, plan, dry_run):
        """Écrire la fiche — sauf en aperçu, où l'on décrit et on s'arrête."""
        if not dry_run:
            fiche.write(valeurs)
            return fiche
        ecarts = self._ecarts(fiche, valeurs)
        if ecarts:
            plan.append(
                "%s « %s » : %s"
                % (self._description, fiche._designation(), ", ".join(sorted(ecarts)))
            )
        return fiche

    @api.model
    def _creer(self, modele, valeurs, plan, dry_run, etiquette):
        """Créer la fiche — sauf en aperçu, où l'on annonce seulement."""
        if dry_run:
            plan.append("%s « %s » : à créer" % (self._description, etiquette))
            return self.env[modele]
        return self.env[modele].create(valeurs)

    def action_push_to_mailcow(self):
        """Pousser vers Mailcow ce qui existe localement.

        Ce qui n'a jamais été créé est créé, ce qui est connu est mis à jour.
        Les fiches archivées sont ignorées : elles ont été retirées du serveur,
        et les repousser le ressusciterait sans qu'on l'ait demandé.
        """
        self._exiger("user")
        creees = mises_a_jour = 0
        a_noter = []
        for fiche in self.filtered("active"):
            if fiche.synced:
                fiche.action_update_on_mailcow()
                mises_a_jour += 1
            else:
                ligne = fiche._creer_sur_mailcow()
                if ligne:
                    a_noter.append(ligne)
                creees += 1
        message = "%d créée(s), %d mise(s) à jour sur Mailcow." % (creees, mises_a_jour)
        if a_noter:
            message += (
                "\n\nMots de passe initiaux, à copier maintenant : Odoo ne les garde pas.\n"
                + "\n".join(a_noter)
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": "Mailcow",
                "sticky": bool(a_noter),
                "message": message,
            },
        }

    def _creer_sur_mailcow(self):
        """Créer une fiche sur le serveur pendant une poussée.

        Renvoie la ligne à montrer une fois à l'administrateur, s'il y en a
        une (le mot de passe initial d'une boîte), sinon None.
        """
        self.ensure_one()
        self.action_create_on_mailcow()
        return None

    def action_forget_locally(self):
        """Retirer la fiche locale sans toucher au serveur.

        On archive plutôt que de supprimer : la fiche sort de la vue, mais
        l'historique reste consultable si on s'est trompé.
        """
        self._exiger("user")
        self.write({"active": False})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": "Mailcow",
                "sticky": False,
                "message": "%d fiche(s) archivée(s). Le serveur n'a pas été touché." % len(self),
            },
        }

    def action_purge_local(self):
        """Supprimer définitivement la fiche locale.

        Le serveur n'est jamais touché : c'est le nettoyage d'un reste local,
        pas une suppression de boîte.
        """
        self._exiger("manager")
        nombre = len(self)
        self.unlink()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": "Mailcow",
                "sticky": False,
                "message": "%d fiche(s) supprimée(s) d'Odoo. Le serveur n'a pas "
                "été touché." % nombre,
            },
        }
