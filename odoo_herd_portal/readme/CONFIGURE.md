Le module n'a pas de réglages `res.config.settings` : il se configure sur les fiches.

1. **Groupe agent** : attribuer **Staging operator (agents)**
   (`odoo_herd_portal.group_staging_operator`) aux comptes des agents. Ce groupe
   autorise le déploiement sur un staging, sa resynchronisation et la demande de mise
   en production ; il ne permet jamais de confirmer une promotion.
2. **Production** (_Odoo Herd_ > _Odoo Instances_, onglet _Portal_) : _Client_,
   _Production approvers_ et _Require two-factor authentication_ (décoché par défaut).
   Sans client, l'instance est invisible du portail ; la recherche propose le filtre
   _Sans client_.
3. **Staging** (même onglet) : _Open to agents_ (décoché par défaut) et _CI accounts_,
   qui peuvent seulement demander une promotion et lire l'état de livraison.
4. **Offres** (_Odoo Herd_ > _Configuration_ > _Instance Templates_, onglet _Portal_) :
   cocher _Offered in the portal_ (décoché par défaut), puis renseigner le cluster, le
   namespace (qui doit déjà exister, avec le secret de pull et le Role de
   `deploy/odoo-herd-clients.yaml`) et le suffixe d'hôte (enregistrement DNS générique
   vers l'ingress).
5. **Double authentification** : le module dépend de `auth_totp` et `auth_totp_portal`.
   Un approbateur qui active la double authentification confirme avec le code de son
   application ; sinon, et si la production n'exige pas la 2FA, il reçoit un code par
   courriel (10 minutes, 5 essais, une demande par minute).
6. **Tâches planifiées** : deux tâches actives toutes les 5 minutes — démarrer les
   promotions planifiées et expirer celles qui sont bloquées, faire avancer les
   demandes de bases approuvées.
