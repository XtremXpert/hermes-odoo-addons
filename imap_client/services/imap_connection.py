# Part of the imap_client Odoo module. See LICENSE for details.
"""Connexion IMAP — imaplib avec SSL, envelopes et corps."""

import contextlib
import imaplib


class IMAPConnexion:
    """Un tunnel IMAP vers la boite d'un compte."""

    def __init__(self, host, port, user, password, use_ssl=True):
        classe = imaplib.IMAP4_SSL if use_ssl else imaplib.IMAP4
        self.srv = classe(host, port)
        self.srv.login(user, password)

    def dossiers(self):
        """La liste des dossiers de la boite."""
        statut, lignes = self.srv.list()
        if statut != "OK":
            return []
        noms = []
        for ligne in lignes:
            # '(\\HasNoChildren) "." "INBOX"' -> 'INBOX'
            brut = ligne.decode() if isinstance(ligne, bytes) else ligne
            noms.append(brut.rsplit(' "', 1)[-1].rstrip('"'))
        return noms

    def entetes(self, dossier, limite=50):
        """Les N derniers messages d'un dossier : uid, sujet, de, date, vu."""
        self.srv.select(dossier, readonly=True)
        statut, data = self.srv.search(None, "ALL")
        if statut != "OK":
            return []
        ids = data[0].split()[-limite:]
        resultats = []
        for ident in reversed(ids):
            statut, charge = self.srv.fetch(
                ident,
                "(UID RFC822.SIZE "
                "BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID IN-REPLY-TO)] "
                "FLAGS)",
            )
            if statut != "OK" or not charge or not isinstance(charge[0], tuple):
                continue
            resultats.append({"imap_id": ident, "raw": charge[0][1], "flags": charge[0][0]})
        return resultats

    def corps(self, dossier, uid):
        """Le message complet d'un uid."""
        self.srv.select(dossier, readonly=True)
        statut, charge = self.srv.uid("fetch", uid.encode(), "(RFC822)")
        if statut != "OK" or not charge or not isinstance(charge[0], tuple):
            return None
        return charge[0][1]

    def marquer_lu(self, dossier, uid):
        """Poser le drapeau \\Seen sur un message."""
        self.srv.select(dossier)
        self.srv.uid("store", uid.encode(), "+FLAGS", "\\Seen")

    def quitter(self):
        with contextlib.suppress(Exception):
            self.srv.logout()
