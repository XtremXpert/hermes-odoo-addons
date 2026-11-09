Pour utiliser ce module, il faut :

1. Configurer le relais courriel avec un jeton (voir Configuration) : c'est lui, et non
   un utilisateur Odoo, qui s'authentifie auprès d'Odoo.
2. Laisser le relais remettre le courriel brut sur `POST /diverse/mail-gateway/process`
   ; Odoo le traite comme un message entrant et l'attache au fil correspondant, qui
   apparaît dans le chatter de l'objet concerné.
3. Suivre les jetons dans _Paramètres_ > _Technique_ > _Mail Gateway_ > _Tokens_ (en
   mode développeur) : nom, date et adresse du dernier usage, nombre d'utilisations,
   expiration, et bascule _Actif_.
4. Révoquer un jeton depuis sa fiche avec **Revoke** : le relais reçoit alors `401` à
   son prochain appel.
5. Retrouver les jetons jamais utilisés ou proches de l'expiration avec les filtres
   _Never used_ et _Expiring soon (next 30d)_.

`GET /diverse/mail-gateway/health` répond toujours `200` : c'est la sonde de vie du
service, sans authentification.
