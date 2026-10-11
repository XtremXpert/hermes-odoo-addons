Ajoute à Discuss un indicateur de traitement pour les conversations privées avec les agents Hermes, convertit le Markdown de leurs réponses en HTML assaini et actualise leur présence dans Odoo.

## Comportement

- La façade `hermes.activity.publier` reçoit les états `working`, `tool`, `done`, `error` ou `cancelled`. Elle valide que la conversation, le message et l'identité correspondent à une requête d'agent authentifiée.
- L'état est stocké sur le canal, puis rendu dans l'interface Discuss par les ressources JavaScript/XML du module. Les mises à jour plus anciennes, répétées ou reçues après un état terminal sont ignorées; l'historique affiché est borné.
- `hermes.activity.repondre` et les messages publiés par un compte Hermes passent le Markdown en HTML, puis l'assainissent. La prise en charge inclut notamment le gras, l'italique, le code, les liens HTTP(S), titres, listes et tableaux. Le HTML fourni par le modèle n'est pas interprété comme contenu actif.
- Le polling de la passerelle actualise la présence du compte. Une tâche planifiée marque hors ligne les agents sans heartbeat récent.

## Accès et dépendances

Dépend de `mail` et `hermes_n1_audit`. Les façades refusent les appels qui ne proviennent pas d'un compte agent identifié et relié à une conversation privée accessible. L'état technique ne peut pas être modifié directement par RPC ordinaire.

## Tests

Les tests couvrent le formatage sûr, l'attribution des réponses, la présence et le traitement des séquences d'activité :

```sh
ADDONS=addons tools/test-modules.sh IMAGE hermes_activity
```

La validation complète de l'image Maison exécute aussi `tools/test-hermes-audit.sh IMAGE`.
