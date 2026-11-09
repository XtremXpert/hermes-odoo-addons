Couche **tenant** de Mailcow : domaines, boîtes mail, alias et adresses de destination,
administrés depuis Odoo par l'API v1 du serveur.

Les fiches se créent, se mettent à jour et se suppriment avec les boutons de l'écran,
qui appellent l'API ; une synchronisation lit l'état du serveur et aligne la copie
locale, sans jamais écrire sur Mailcow. Les listes se rafraîchissent d'elles-mêmes à
l'ouverture si la copie date de plus d'une minute, et les fiches absentes du serveur
sont marquées « non synchronisées » plutôt que supprimées.

Les mots de passe — initial d'une boîte, réinitialisation, mot de passe applicatif —
sont fabriqués par Odoo, affichés une seule fois et stockés nulle part. Trois groupes
règlent les droits : _Lecture et synchronisation_ pour les agents, _Utilisateur_ pour
créer et mettre à jour, _Gestionnaire_ pour supprimer, changer les mots de passe et
administrer. Le module porte aussi les réglages de connexion et les données des tableaux
de bord, dont les écrans d'ensemble vivent dans `mailcow`.
