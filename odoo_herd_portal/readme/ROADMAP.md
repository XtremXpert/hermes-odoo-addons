## Limites connues

- **Hypothèse du code par courriel** : le code à six chiffres ne prouve quelque
  chose que si aucun agent ne peut lire ou détourner la boîte de l'approbateur.
  Ce point est vérifié **dans Odoo** — les comptes `hermes_n1`, `hermes_n2`,
  `hermes_n3` et `hermes_n3_executor` ne lisent ni `mail.mail` ni Mailcow — mais
  pas en dehors (accès au serveur de courriel, connecteurs de messagerie d'un
  agent). `readme/DESCRIPTION.md` recommande une adresse hors de portée des
  agents, ou la double authentification.
- **Double authentification non imposée par défaut** : *Require two-factor
  authentication* est décoché sur une production ; sans 2FA sur le compte de
  l'approbateur, le code par courriel est le seul facteur.
- **Déploiement non suivi en direct** : « Terminée » sans modules signifie que
  l'image a été demandée à l'opérateur ; le déploiement lui-même se suit dans
  l'état de l'instance (`readme/DESCRIPTION.md`).
- **Mot de passe d'une base neuve non récupérable** : il n'existe que dans un
  `mail.mail` supprimé après envoi. Si l'envoi échoue, le courriel reste en file ;
  s'il est perdu, il faut réinitialiser le mot de passe du compte par `odoo
  shell` sur l'instance — aucun self-service.
- **Resynchronisation inter-cluster conditionnée** : elle restaure la **dernière
  sauvegarde S3 terminée** de la production ; sans sauvegarde, la demande est
  refusée.
- **Staging fermé aux agents** : un compte CI n'y peut que demander une promotion
  et lire l'état de livraison — ni déploiement, ni resynchronisation, ni
  annulation.
- **Délais fixes** : confirmation valable 10 minutes, 5 essais, une demande par
  minute ; promotion sans nouvelles du cluster abandonnée après 6 h, demande de
  base en échec après 3 h ; deux tâches planifiées toutes les 5 minutes.
- **Dette de lint assumée** : `.pre-commit-config.yaml` exclut `odoo_herd_portal`
  et `odoo_herd` d'ESLint jusqu'à une PR dédiée.

## Pistes

- Retirer l'exclusion ESLint annoncée dans `.pre-commit-config.yaml` (« le temps
  d'une PR à part ») une fois le nettoyage JS fait.
