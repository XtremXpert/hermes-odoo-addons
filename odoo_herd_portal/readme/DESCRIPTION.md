# Odoo Herd Portal

Portail client pour une production Odoo gérée par `odoo_herd` et ses stagings
(`/my/odoo`). Un client sans base peut en demander une (voir « Nouvelle base »).
Deux actions sur une base existante :

- **Resynchroniser le staging depuis la production** : copie neutralisée de la base
  et du filestore (`OdooStagingRefreshJob`, `neutralize` forcé, source = la production
  du staging). Ouverte au client et aux agents, sans confirmation : le staging est
  jetable et ne peut jamais viser une production.
- **Passer la production au code du staging** : crée une demande de mise en
  production (`k8s.odoo.promotion`) qui fige l'image du staging par son empreinte
  (`…@sha256:`). Rien ne se passe tant qu'un **humain approbateur** ne l'a pas
  confirmée.

## Flux

```
agent / client ── demande ──► en attente ──► code par courriel ──► confirmée ──► planifiée?
                                              (approbateur)                       │
production ◄── mise à jour des modules ◄── image ◄── sauvegarde ◄──────────────────┘
               (si demandée)            (spec.image seule)  (échec = production intacte)
```

## Barrière humaine

- Seuls les **approbateurs** listés sur la production (onglet Portail) confirment,
  depuis le portail ou depuis le backend (bouton « Confirmer » de la mise en
  production, assistant `k8s.odoo.promotion.confirm` : mêmes contrôles privés, un
  mauvais code reste compté). La méthode est choisie par le serveur :
  - **double authentification activée** sur le compte (`/my/security`, `auth_totp_portal`)
    → **code de l'application d'authentification**, vérifié par Odoo lui-même
    (`_check_credentials` type `totp` : limite d'essais par utilisateur, code rejoué
    refusé). Le code par courriel est alors refusé ;
  - sinon, si la production a **« Exiger la double authentification »** → refus, avec
    un lien pour l'activer ;
  - sinon → **code à 6 chiffres envoyé par courriel** (10 min, 5 essais, une demande
    par minute), qui fonctionne aussi pour les comptes OIDC sans mot de passe Odoo.
  La méthode utilisée est enregistrée sur la mise en production (« Confirmée avec »). Seule une empreinte HMAC du code est stockée, illisible par l'ORM ;
  le courriel est un `mail.mail` supprimé après envoi, sans message dans le chatter
  (testé : un agent ne retrouve le code ni dans `mail.message` ni dans `mail.mail`).
- **Hypothèse** : aucun agent ne peut lire la boîte courriel d'un approbateur. Vérifié
  en production le 2026-10-06 côté Odoo (les comptes `hermes_n1`, `hermes_n2`,
  `hermes_n3`, `hermes_n3_executor` n'écrivent pas dans Mailcow et ne lisent pas
  `mail.mail`), pas en dehors d'Odoo (accès au serveur de courriel, connecteurs de
  messagerie d'un agent). Si un agent peut lire ou détourner cette boîte, le code ne
  prouve plus rien : donner à l'approbateur une adresse hors de portée des agents.
  Cocher « Exiger la double authentification » sur une production supprime cette
  hypothèse : le secret TOTP reste sur le téléphone de l'approbateur.
- **Agents** = membres de « Opérateur de staging (agents) » ou d'un groupe d'un module
  `hermes_*`. Ils ne confirment jamais, même ajoutés aux approbateurs, et ne peuvent
  modifier ni l'image d'une production, ni l'environnement, les approbateurs, le
  client, l'ouverture aux agents ou les comptes CI d'une instance — même en `sudo`
  (contrôle sur le groupe, jamais sur le contexte).
- La confirmation et le démarrage sont des méthodes privées (`_herd_*`), injoignables
  en RPC autrement que par les routes du portail et l'assistant du backend, qui
  passent l'utilisateur réel aux contrôles ; personne n'a de droit d'écriture sur
  `k8s.odoo.promotion`.
- Une demande confirmée est figée (image, modules, horaire, instances). Une
  modification avant confirmation annule le code envoyé.
- Une seule mise en production à la fois par production ; au démarrage, une demande
  dont la production a changé depuis (image différente) est refusée au lieu de la
  ramener en arrière.
- « Terminée » sans modules signifie que l'image a été demandée à l'opérateur ;
  le déploiement lui-même se suit dans l'état de l'instance.
- Le changement d'image n'envoie que `spec.image` (pas `_patch_to_cluster`, qui
  enverrait tous les champs non synchronisés). L'image précédente est gardée pour un
  retour arrière.

## Nouvelle base (client sans base)

Un client dont l'entité commerciale n'a encore aucune production voit la tuile
« Instances Odoo » à 0, avec « Ajouter une base ». Le wizard `/my/odoo/new` lui fait
choisir une **offre** et un **nom** ; il crée une demande `k8s.odoo.instance.request`
(`BASE/0001`…). Rien n'est créé dans le cluster avant qu'**un humain gestionnaire**
(`odoo_herd.group_k8s_manager`, jamais un agent) ne l'approuve dans Odoo Herd →
Demandes de bases.

```
client ── demande ──► en attente ──► approuvée ──► production neuve, sans hôte public
                       (gestionnaire)              │ phase Running
                                                   ▼
      admin/admin remplacé par le compte du client (XML-RPC par le proxy de l'API)
                                                   ▼
       hôte réel posé, accès envoyé par courriel ──► staging clone_prod ──► prête
```

- **Offres** : modèles d'instance cochés « Proposé au portail » (onglet Portail du
  modèle), avec cluster, namespace et suffixe d'hôte. Hôtes : `<nom>.<suffixe>` et
  `<nom>-staging.<suffixe>` ; base `<nom>` (tirets en soulignés) et `<nom>_staging`.
- **Nom** : 3 à 30 caractères (minuscules, chiffres, tirets simples), noms réservés
  refusés, et libre partout : instances connues de l'herd, hôtes déjà servis, autres
  demandes. Une seule demande en cours par client ; aucune si le client a déjà une
  production.
- **Compte admin** : une base neuve (`odoo -i base`) a `admin/admin`. La production est
  donc créée avec un hôte provisoire `<nom>.herd-pending.invalid`, injoignable. Dès
  qu'elle est `Running`, l'herd remplace `admin/admin` par le courriel du client et un
  mot de passe aléatoire, par XML-RPC à travers le proxy de Service de l'API
  Kubernetes, puis seulement pose l'hôte réel. En cas d'échec, la production reste
  injoignable et la demande passe en échec.
- **Mot de passe** : il n'existe que dans un `mail.mail` supprimé après envoi, jamais
  dans le chatter ; la transaction est validée dès ce courriel mis en file, avant de
  poser l'hôte et de créer le staging (étapes reprises par la tâche planifiée si elles
  échouent). Si l'envoi échoue, le courriel reste dans la file (Configuration →
  Technique → Courriels) jusqu'à son envoi ; s'il est perdu, réinitialiser le mot de
  passe du compte du client dans sa base (`odoo shell` sur l'instance). Le mot de passe
  maître de l'opérateur est aléatoire et jamais montré (`list_db` est coupé par
  l'opérateur). Le demandeur doit avoir un courriel : c'est son identifiant.
- **Staging** : créé ensuite par clonage neutralisé de la production (`clone_prod`),
  fermé aux agents. La production a pour client l'entité du demandeur, et le demandeur
  pour approbateur des mises en production.
- **Progression** : relancée à chaque changement de phase (webhook ou synchronisation),
  plus une tâche planifiée toutes les 5 min ; échec après 3 h sans nouvelles.

**Mise en place**, sur chaque cluster qui porte une offre : appliquer
`deploy/odoo-herd-clients.yaml` (namespace `odoo-clients`, et `services/proxy` pour
odoo-herd dans ce seul namespace), copier le secret de pull d'image dans ce namespace,
et vérifier que le suffixe d'hôte a un enregistrement DNS générique vers l'ingress.

**Copies neutralisées** : `data/neutralize.sql` désactive tous les clusters, pour
qu'un staging de l'herd ne crée, ne promeuve ni ne resynchronise jamais rien sur un
vrai cluster.

## Flux de livraison de maison

1. **Staging** : resynchroniser `maison-staging` depuis la production, y déployer l'image
   de la branche `20.0` par son digest, puis installer ou mettre à jour les modules sur
   `maison_staging` et tester.
2. **Demande** : sur `/my/odoo`, « Passer la production au code de ce staging », avec
   les *modules à mettre à jour* (`-u`) et les *nouveaux modules à installer* (`-i`), tels
   que testés sur le staging. Un agent peut préparer cette demande.
3. **Confirmation humaine** : un approbateur la confirme avec son application
   d'authentification. La promotion fait alors une sauvegarde, applique l'image
   (`spec.image` seule), puis lance un seul `OdooUpgradeJob` (`-u` et `-i`).

`tools/promote-production.py` ne sert plus qu'en secours.

## Resynchroniser un staging

« Resynchroniser » remplace la base et le filestore du staging par une copie neutralisée de sa production :

- **même cluster et même namespace :** l'opérateur clone la production (`OdooStagingRefreshJob`) ;
- **autre cluster** (diverse-odoo : prod sur rke01 OVH, staging sur le cluster maison) : il restaure la **dernière sauvegarde S3 terminée** de la production, filestore compris (`OdooRestoreJob`). Sans sauvegarde, la demande est refusée. Le cluster du staging doit avoir le secret S3 nommé dans `k8s.s3.config`.

## Pour les agents (RPC, groupe « Opérateur de staging »)

Sur un staging coché « Ouvert aux agents » :

```python
env["k8s.odoo.promotion"].herd_deploy_staging(staging_id, "ghcr.io/…@sha256:…")
env["k8s.odoo.promotion"].herd_resync_staging(staging_id)
env["k8s.odoo.promotion"].herd_request_promotion(
    staging_id, modules="sale,stock", scheduled_at="2026-10-07 02:00:00"
)
```

### Comptes CI sur un staging fermé aux agents

Un staging qui contient des données réelles (diverse-odoo) reste fermé aux agents.
Pour que la CI y demande quand même la promotion, inscrire son compte dans
« Comptes CI » du staging : il peut alors appeler `herd_request_promotion` et
`herd_staging_status`, **et rien d'autre** (ni déploiement, ni resynchronisation,
ni annulation). Le compte CI reste un agent : il ne confirme jamais et ne touche
jamais une production.

## Mise en place

1. Sur la production : client, approbateurs, et « Exiger la double authentification »
   pour une vraie production de client (onglet Portail).
2. Créer le staging (`environment = staging`, `production_instance_id` = la production),
   cocher « Ouvert aux agents » si besoin, ou seulement y inscrire le compte de la CI
   dans « Comptes CI ».
3. Donner le groupe « Opérateur de staging (agents) » au compte de l'agent, sans
   aucun groupe `odoo_herd`.

Tâches planifiées toutes les 5 min : démarrer les mises en production planifiées et
abandonner celles sans nouvelles du cluster depuis 6 h ; faire avancer les demandes de
bases approuvées.

Tests : `ADDONS=addons tools/test-modules.sh IMAGE odoo_herd_portal`.
