1. Donner le groupe **Mail Gateway Administrator** à la personne qui gère les jetons
   (il implique Administration / Paramètres).
2. En mode développeur, ouvrir *Paramètres → Technique → Mail Gateway → Generate Token*,
   saisir un libellé (par exemple `relais-courriel`) et cliquer **Generate**.
3. Copier le jeton affiché **tout de suite** : il ne sera plus jamais visible. Le placer
   dans la configuration du relais, jamais dans un dépôt.
4. Vérifier depuis le relais : `POST /diverse/mail-gateway/check` avec l'en-tête
   `X-Mail-Gateway-Token` doit répondre `{"ok": true, …}`.

Derrière un mandataire qui termine TLS, Odoo doit tourner avec `--proxy-mode`. Pour un
banc d'essai en HTTP clair seulement, le paramètre système
`diverse_mail_gateway.allow_http` à `True` lève le refus du HTTP.
