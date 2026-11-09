Le module ne connaît que trois niveaux (`n1`, `n2`, `n3`). L'URL de retour
acceptée est calculée à partir de l'hôte de la requête : le tableau de bord doit
donc être servi sur le même hôte qu'Odoo, sinon l'autorisation est refusée
(400). Un déploiement sur un autre domaine demanderait une évolution.

L'échange du code ne s'appuie sur aucun secret client : le tableau de bord n'est
pas authentifié en tant que client, seulement par le code à usage unique et le
vérificateur PKCE. La sécurité repose donc entièrement sur le stockage haché du
code, son expiration à 60 secondes et la revérification des droits
d'administrateur au moment de l'échange.

Le code est brûlé même quand l'échange échoue : c'est voulu, mais cela impose de
relancer tout le flux après une erreur de vérificateur. Il n'y a pas de jeton de
rafraîchissement côté Odoo : le tableau de bord émet ensuite sa propre session
d'une heure, et la connexion par mot de passe du tableau de bord reste
disponible en secours.
