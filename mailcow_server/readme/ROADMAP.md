## Limites connues

- **Squelette sans fonctionnalité** : le module n'ajoute ni menu, ni vue, ni
  modèle ; son seul contenu est son manifeste et un `__init__.py` vide. Les
  outils d'entretien annoncés (état de l'instance, relais SMTP, quarantaine
  globale) ne sont pas écrits — `readme/DESCRIPTION.md` les donne comme à venir.
- **Aucun test** : le dossier `tests/` est absent, faute de code à éprouver.
- **Dépendance déclarée mais inutilisée** : le manifeste dépend de
  `mailcow_tenant`, mais aucun code n'importe ses services. La dépendance est une
  intention de réutilisation (client API, groupes), pas un lien actif.
- **Statut `Beta`** : `development_status` vaut `Beta` et la version est
  `20.0.1.0.0`.

## Pistes

- Écrire les outils d'entretien annoncés dans la description du module, en
  réutilisant `mailcow_tenant/services/mailcow_client.py` et ses groupes plutôt
  qu'un second client.
