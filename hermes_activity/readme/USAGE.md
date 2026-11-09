Pour utiliser ce module, il faut :

1. Ouvrir _Discussion_ et une conversation privée avec un agent Hermes : le module
   n'ajoute ni menu ni réglage, tout se passe dans le fil.
2. Suivre le bandeau d'activité au-dessus de la zone de saisie : nom de l'agent, état
   (`working`, `tool`, `done`, `error` ou `cancelled`), durée, et le détail
   _Étapes du traitement_ avec la durée de chacune.
3. Sur une invite d'approbation du framework Hermes, cliquer l'un des boutons
   **Approuver**, **Pour la session**, **Toujours (permanent)** ou **Refuser** : la
   commande est postée au nom de la personne qui clique. Sans JavaScript, le lien
   ouvre une page de confirmation dont le formulaire porte le jeton CSRF.
4. Lire les réponses des agents mises en forme (gras, italique, code, liens HTTP(S),
   titres, listes et tableaux) sans que le HTML fourni par le modèle soit exécuté.

L'état affiché est borné à l'historique récent ; les mises à jour anciennes, répétées
ou reçues après un état terminal sont ignorées. Une tâche planifiée marque hors ligne
les agents dont la présence n'a pas été rafraîchie.
