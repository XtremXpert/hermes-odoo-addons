Le module de l'usage téléphonique d'un tenant : ses postes, son journal
d'appels, son tableau de bord et son téléphone dans le navigateur. Il ne crée
pas l'infrastructure — le tenant, son contexte et ses plages sont l'affaire de
`wazo_server` — et il ne crée pas non plus les modèles d'exploitation, qui
vivent dans `wazo_tenant` : il apporte la couche d'usage côté Odoo et les
extensions dont un tenant a besoin. C'est le module qu'installe le client, avec
`wazo_tenant`, et jamais `wazo_server`.

Techniquement, le module n'a aucun modèle à lui : il étend `wazo.user`,
`wazo.cdr`, `res.users` et `res.config.settings`. Le softphone parle directement
à Wazo en SIP-over-WSS, sans relay : pour un endpoint généré par Wazo, l'AOR de
l'en-tête `From` est le nom de l'endpoint et non l'extension, d'où deux valeurs
séparées (`aor` et `auth_user`). Le pont vers le module *voip* d'Odoo Enterprise
est optionnel : sans ce module, il est un no-op, et `wazo_phone` reste
utilisable avec un poste SIP classique.

Les fichiers d'actifs sont chargés « après le chargeur » (`after
web/static/src/module_loader.js`) parce qu'Odoo trie les modules du paquet et
place `wazo_phone` avant `web` : sans cette directive, `odoo.define` n'existe
pas encore et le client web reste blanc sans erreur serveur. Les bibliothèques
`static/lib/sip.js` et `static/lib/wazo-sdk.js` sont vendorisées ; le SDK est
chargé à la demande, seulement quand le moteur SDK est choisi. Le module dépend
de `wazo_tenant`, `web` et `mail`, et documente ses écrans dans
`doc/ADMINISTRATEUR.md` et `doc/UTILISATEUR.md`.
