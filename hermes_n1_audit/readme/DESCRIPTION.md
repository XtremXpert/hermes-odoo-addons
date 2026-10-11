Le module `hermes_n1_audit` 20.0.3.0.1 permet au bot de travailler sur les objets
métier avec les droits ORM du demandeur Discuss authentifié. Le serveur vérifie
le message source, son auteur administrateur, son âge (une heure maximum) et la
conversation privée avec le bot. Le groupe `hermes_n1_audit.group_agent` autorise
la façade ; aucun droit administrateur ni droit général d'écriture n'est ajouté
au bot. Aucun `sudo` ne modifie les objets métier.

## Façade métier

- `explorer` découvre les modèles persistants, les champs lisibles/éditables et
  les actions disponibles ; pas de liste fixe de modèles métier.
- `lire_metier` fournit les objets, leur total exact et la pagination (80 maximum).
  `include_archived=True` permet de retrouver les objets archivés.
- `corriger_metier` crée ou corrige un objet : descriptions HTML, champs éditables
  et liens vers des objets existants. Les valeurs précédentes sont obligatoires
  pour une correction. Les affectations `user_id`/`user_ids` peuvent référencer
  des utilisateurs internes actifs, sans modifier leur compte.
- `agir_metier` archive, réactive ou supprime un objet. Il exige les valeurs
  précédentes, dont `write_date`, conservé à la microseconde pour détecter une
  modification concurrente même dans la même seconde.

Chaque mutation et son journal immuable sont atomiques. Une note est publiée
sur le chatter de l'objet, ou sur le journal central pour les objets sans
chatter et les suppressions. Lorsqu'un objet et son chatter sont supprimés, les notes déjà référencées par
le journal sont déplacées vers celui-ci, en conservant leurs identifiants et leur
contenu. Un échec du journal annule l'opération. Le résultat
retourne `audit_id` et `chatter_message_id`. Les rejeux identiques sont idempotents,
même si la réponse réseau précédente a été perdue.

Les objets techniques, secrets, binaires et champs de contrôle restent exclus.
Les relations n'autorisent pas de création, modification ou suppression imbriquée :
chaque objet doit avoir sa propre opération auditée. Les méthodes arbitraires de
validation de documents ne sont pas exposées ; les documents financiers ou
logistiques validés restent protégés contre la correction directe.

## Compatibilité et livraison

Les anciens appels `modifier`/`capabilities` conservent leur liste de champs et
leur comportement historique. Ils ne décrivent pas les capacités de la façade
métier moderne. Livrer ce module avant les nouveaux outils et le SOUL N1.

Tests : `bash tools/test-hermes-audit.sh IMAGE`, avec PostgreSQL éphémère.
La suite `TestAudit` couvre descriptions HTML de projets, affectations de tâches,
refus d'accès et de relations imbriquées, archivage/suppression, rejeu, concurrence,
contexte falsifié, journal indisponible et immutabilité.

## Copies neutralisées

`data/neutralize.sql` est exécuté par `odoo neutralize` (clone de staging par l'opérateur,
resynchronisation odoo_herd ou portail) : tout compte membre d'un groupe d'un module
`hermes_*` y est désactivé et perd ses clés API. Une copie ne peut donc jamais être
pilotée par un agent, même avec des clés clonées de la production. Rien à faire après
une resynchronisation.
