Un parc d'instances Odoo tourne sur Kubernetes, piloté par l'opérateur Bemade
(ressources `OdooInstance`, `OdooBackupJob`, `OdooUpgradeJob`, …). Sans outil,
chaque création, sauvegarde, restauration, mise à jour ou resynchronisation de
staging se fait en kubectl et en YAML. `odoo_herd` ramène ces gestes dans Odoo :
clusters, instances, modèles d'instance, sauvegardes S3/MinIO, travaux et
tableau de bord, y compris pour un staging hébergé sur un autre cluster.

L'approche sépare nettement ce qui est **désiré** de ce qui est **constaté**. La
fiche d'une instance garde les champs éditables à envoyer et des champs
`current_*` relus du cluster ; *Sync to Cluster* n'envoie que les champs
modifiés (`edited_fields`), *Reset to Current* revient aux valeurs du cluster.
Les travaux de l'opérateur sont créés **après le commit** de la transaction — un
retry Odoo ne doit pas relancer trois fois le même travail — et leur état est
relu du cluster par une tâche planifiée, parce qu'un webhook peut se perdre quand
Odoo redémarre à la fin d'une mise à jour.

Les webhooks HTTP des travaux sont `auth="public"` et protégés par un jeton
Bearer propre à chaque travail ; l'état d'une instance passe par un webhook de
cluster, avec un jeton en paramètre d'URL. Sans retour du webhook, la tâche de
relecture reprend la main au bout de deux minutes. C'est le socle de `odoo_herd_portal`,
qui y ajoute la barrière humaine des mises en production et les façades des
agents. Le module vient de Bemade Inc., porté en 20.0 par Diverse-Cité ; il
dépend de bibliothèques Python hors Odoo (`kubernetes`, `pyyaml`, `boto3`,
`openupgradelib`).

## Modèle de données

| Modèle | Champs clés | Relations |
| ------ | ----------- | --------- |
| `k8s.cluster` | name, api_endpoint, default_namespace, connection_status | « modèle par défaut » : → `k8s.odoo.instance.template` (n-1) ; « config S3 » : → `k8s.s3.config` (n-1) ; « instances » : ← `k8s.odoo.instance` (1-n) |
| `k8s.odoo.instance` | name, environment, phase, url | « cluster » : → `k8s.cluster` (n-1) ; « production d'un staging » : → `k8s.odoo.instance` (n-1) |
| `k8s.odoo.instance.template` | name, image, filestore_size, initialization_mode | « clusters » : ← `k8s.cluster` (1-n) |
| `k8s.s3.config` | name, endpoint, bucket, region | « clusters » : ← `k8s.cluster` (1-n) ; « sauvegardes » : ← `k8s.odoo.backup` (1-n) |
| `k8s.odoo.backup` | name, state, object_key, bucket | « instance » : → `k8s.odoo.instance` (n-1) ; « cluster » : → `k8s.cluster` (n-1) ; « config S3 » : → `k8s.s3.config` (n-1) ; « planification » : → `k8s.odoo.instance.backup.schedule` (n-1) |
| `k8s.odoo.restore` | name, state, neutralize | « sauvegarde source » : → `k8s.odoo.backup` (n-1) ; « instance cible » : → `k8s.odoo.instance` (n-1) ; « cluster » : → `k8s.cluster` (n-1) |
| `k8s.odoo.upgrade` | name, state, modules, modules_install | « instance » : → `k8s.odoo.instance` (n-1) ; « cluster » : → `k8s.cluster` (n-1) |
| `k8s.odoo.staging.refresh` | name, state, filestore_method | « staging cible » : → `k8s.odoo.instance` (n-1) ; « production source » : → `k8s.odoo.instance` (n-1) ; « cluster » : → `k8s.cluster` (n-1) |
| `k8s.odoo.instance.backup.schedule` | interval_number, interval_type, keep_count | « instance » : → `k8s.odoo.instance` (n-1) ; « cluster » : → `k8s.cluster` (n-1) ; « sauvegardes » : ← `k8s.odoo.backup` (1-n) |
| `k8s.spec.viewer` | title, content | — (modèle transitoire) |
| `k8s.backup.wizard` | format, with_filestore | « instance » : → `k8s.odoo.instance` (n-1) ; « cluster » : → `k8s.cluster` (n-1) |
| `k8s.cluster.test.wizard` | state, test_result | « cluster » : → `k8s.cluster` (n-1) |
| `k8s.create.instance.wizard` | name, environment, initialization_mode | « cluster » : → `k8s.cluster` (n-1) ; « modèle » : → `k8s.odoo.instance.template` (n-1) ; « production source » : → `k8s.odoo.instance` (n-1) ; « sauvegarde source » : → `k8s.odoo.backup` (n-1) |
| `k8s.delete.instance.wizard` | instance_name, confirmation_text | « instance » : → `k8s.odoo.instance` (n-1) |
| `k8s.restore.backup.wizard` | confirmation_name, neutralize | « sauvegarde » : → `k8s.odoo.backup` (n-1) ; « instance cible » : → `k8s.odoo.instance` (n-1) ; « cluster » : → `k8s.cluster` (n-1) |
| `k8s.staging.refresh.wizard` | confirmation_name, filestore_method | « staging cible » : → `k8s.odoo.instance` (n-1) ; « production source » : → `k8s.odoo.instance` (n-1) ; « cluster » : → `k8s.cluster` (n-1) |
| `k8s.sync.instances.wizard` | sync_all, state | « clusters » : ↔ `k8s.cluster` (n-n) |
| `k8s.upgrade.wizard` | modules, modules_install | « instance » : → `k8s.odoo.instance` (n-1) |
| `k8s.upload.backup.wizard` | backup_name, state, object_key | « instance » : → `k8s.odoo.instance` (n-1) ; « cluster » : → `k8s.cluster` (n-1) |
