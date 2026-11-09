Pour utiliser ce module, il faut :

1. Préparer les droits, le client, les approbateurs et l'offre publiée (voir
   Configuration) ; les agents ne confirment jamais une mise en production.
2. Côté client, ouvrir le portail à l'adresse `/my/odoo`. Sans base, la tuile
   _Odoo instances_ propose **Add a database** : choisir une offre et un nom, puis
   **Send the request**. Un gestionnaire (_K8s Manager_) approuve la demande dans
   _Odoo Herd_ > _Database requests_ avec **Approve and create**, ou la refuse.
3. Sur la page d'une base, **Resync staging from production** remplace la base et le
   filestore du staging par une copie neutralisée de la production.
4. **Move production to this staging's code** (ou **Update the production's modules**
   quand l'image est déjà la même) crée une mise en production : renseigner les modules
   à mettre à jour (`-u`), les nouveaux modules à installer (`-i`) et, éventuellement,
   l'heure. Rien n'est déployé tant qu'un approbateur ne confirme pas.
5. L'approbateur confirme depuis le portail, ou depuis la fiche de la mise en
   production (_Odoo Herd_ > _Backup/Restore_ > _Promotions_, bouton **Confirm**) :
   code de l'application d'authentification si la double authentification est active,
   sinon **Send me a confirmation code** puis le code reçu par courriel. Une
   sauvegarde de la production est prise avant tout changement.
6. Suivre les demandes et les promotions dans _Odoo Herd_ > _Database requests_ et
   _Odoo Herd_ > _Backup/Restore_ > _Promotions_.

Un agent appelle par RPC `herd_deploy_staging`, `herd_resync_staging` et
`herd_request_promotion` sur un staging ouvert aux agents ; un compte CI peut seulement
demander une promotion et lire l'état de livraison avec `herd_staging_status`.
