Connecteur **Wazo Platform**, module d'**un tenant** Wazo.

- connexion au serveur Wazo (URL, jeton d'API, tenant) par les réglages ;
- création d'utilisateurs Wazo (ligne SIP, poste, endpoint, messagerie vocale) depuis un
  contact Odoo ;
- création de groupes d'appel (_ring groups_) : poste pris dans la plage des groupes du
  contexte, membres rattachés par utilisateur Wazo et ordonnés par priorité de sonnerie ;
- inventaire des postes du contexte : rattachements, postes orphelins, correspondance
  avec les fiches Odoo ;
- journal d'appels synchronisé depuis `wazo-call-logd` (tâche planifiée et bouton
  manuel), statistiques d'appels par contact ;
- softphone WebRTC dans Odoo (moteurs sip.js et SDK Wazo).

Les **plages d'extensions** sont lues dans Wazo (`contextnumbers`) au lieu d'être
recopiées : un poste hors plage, d'un autre type, ou déjà en service, est refusé
**avant** toute écriture distante.
