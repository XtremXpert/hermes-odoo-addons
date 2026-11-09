L'opérateur d'un tenant Wazo exploite la téléphonie de son client depuis Odoo :
usagers et postes, groupes d'appel, files d'attente, menus vocaux, salles de
conférence, parcs de stationnement, messageries vocales, et le journal
d'appels. C'est la couche « exploitation d'un tenant », par opposition à
`wazo_server` (l'exploitant de la plateforme) et à `wazo_phone` (l'usage :
tableau de bord, bouclage d'appel, softphone).

Le PBX fait autorité : chaque objet porte un état `new` / `synced` / `error`,
un message d'erreur et les identifiants distants qui permettent une reprise
idempotente. Les flux de création sont multi-appels — poste, ligne, utilisateur,
messagerie puis compte d'authentification pour un usager ; groupe, poste puis
remplacement de l'ensemble des membres pour un groupe d'appel — et un échec
indique l'étape. Chaque écriture distante est définitive même si la transaction
Odoo est annulée par la suite. Les plages d'extensions sont lues dans Wazo
(`contextnumbers`), et un numéro hors plage, d'un autre type ou déjà en service
est refusé avant toute écriture.

Deux objets méritent leur forme : le membre de groupe d'appel est un modèle — et
non un `Many2many` — parce qu'il porte la priorité de sonnerie ; l'inventaire des
postes est un modèle transitoire reconstruit à chaque chargement, seul moyen de
voir les extensions orphelines que rien d'autre n'affiche. Le journal d'appels
est une copie synchronisée depuis `wazo-call-logd` par une tâche planifiée
(toutes les heures, inactive par défaut) ou par le bouton manuel — pas en temps
réel. Les réglages portent URL, jeton, tenant, contexte des lignes, langue des
messageries et vérification TLS ; `wazo_phone` étend ces modèles, `wazo_server`
s'appuie dessus et `wazo_voipms` route les DID vers leurs destinations.

## Modèle de données

| Modèle | Champs clés | Relations |
| ------ | ----------- | --------- |
| `wazo.tenant` | name, slug, remote_uuid, last_seen_at | — (fiche alimentée par `action_sync_from_wazo`) |
| `wazo.user` | name, extension, wazo_state | « contact » : → `res.partner` (n-1, externe) ; « membres » : ← `wazo.ring.group.member` (1-n) ; « groupes » : ↔ `wazo.queue` (n-n) |
| `wazo.ring.group` | name, extension, ring_strategy, wazo_state | « membres » : → `wazo.ring.group.member` (1-n) |
| `wazo.ring.group.member` | priority, extension | « groupe » : → `wazo.ring.group` (n-1) ; « utilisateur » : → `wazo.user` (n-1) |
| `wazo.queue` | name, extension, wazo_state | « agents » : ↔ `wazo.user` (n-n) |
| `wazo.ivr` | name, menu_sound, timeout, max_tries | — (pas de poste) |
| `wazo.conference` | name, extension, pin, max_users | — |
| `wazo.parking` | name, extension, slots_start, slots_end | — |
| `wazo.voicemail` | name, number, language, wazo_state | — |
| `wazo.cdr` | call_direction, caller_num, answered, date_start | « contact » : → `res.partner` (n-1, externe) ; « enregistrement » : → `ir.attachment` (n-1, externe) |
| `wazo.extension.inventory` | extension, attachment_kind, is_orphan | — (modèle transitoire) |
