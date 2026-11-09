Les anciens appels `modifier`/`capabilities` restent bornés à douze modèles et à
une liste de champs fixe (`WRITE_FIELDS`) : ils ne décrivent pas la façade
moderne et ne couvrent pas d'autres modèles.

La façade moderne exclut par préfixe les modèles techniques (`ir.`, `base.`,
`hermes.`, `k8s.`…), interdit les créations, modifications et suppressions
imbriquées dans les relations, et refuse de corriger un document validé. Une
opération sensible doit donc passer par le workflow Odoo ou par N3, pas par
cette façade.

Le contrôle de concurrence s'appuie sur les valeurs précédentes. Or
`values_match` ignore la comparaison d'un champ dont la valeur attendue contient
un jeton de pseudonymisation : ces champs ne peuvent pas être vérifiés, donc une
écriture concurrente y échappe au contrôle.

Le journal est immuable : `write` et `unlink` y lèvent toujours une erreur, il
n'a pas d'écran et ne se lit que par RPC. Une erreur de saisie ne se corrige
pas, elle se documente autrement. Enfin, la neutralisation des copies dépend de
l'exécution de `data/neutralize.sql` par `odoo neutralize` ; sans cette étape,
un staging cloné garde des comptes d'agent actifs.
