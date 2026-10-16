Administrer un serveur **Mailcow** depuis Odoo, par son API REST v1 (`X-API-Key`).

- gestion des domaines, boîtes mail et alias du serveur Mailcow ;
- création, mise à jour et suppression sur le serveur par des boutons ;
- synchronisation (import) depuis le serveur Mailcow ;
- mots de passe initiaux et de réinitialisation générés par Odoo, affichés une
  seule fois et jamais stockés, ni dans une fiche ni dans un assistant ;
- droits vérifiés dans chaque méthode, pas seulement sur les boutons : le groupe
  Lecture et synchronisation (pour les agents) lit et aligne Odoo sur le serveur,
  sans jamais écrire sur Mailcow ni voir de mot de passe ; le groupe Utilisateur
  crée et met à jour ; le groupe Gestionnaire supprime, synchronise et change les
  mots de passe ;
- une écriture n'est jamais rejouée : après une erreur passagère ou un délai
  dépassé (30 s), le résultat est annoncé incertain, à relire par une
  synchronisation ;
- configuration de la connexion (URL et clé API) dans les réglages ;
- tableau de bord : occupation des domaines, plafonds atteints, pression des quotas.
