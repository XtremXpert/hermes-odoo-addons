# Les instruments qui ont menti

Écrit après la restructuration des modules sous `addons/`. Huit fois, un contrôle
a accusé le dépôt ; huit fois, l'instrument était en cause. À relire avant de
conclure qu'une chose est cassée — et à citer quand on écrit un nouveau contrôle.

## 1. `git check-ignore` répond sur un chemin qui n'existe pas

Contrôle prévu : « le poc reste-t-il ignoré sous son nouveau chemin ? » Posée sur
`addons/wazo_phone/poc/…` alors que le dossier vivait encore à l'ancien chemin,
la commande a répondu « ignoré ». C'était faux : git compare le motif au **texte**
du chemin. Le motif ancré `/wazo_phone/poc/` avait cessé de correspondre, et les
22 fichiers qui portent un vrai mot de passe étaient redevenus visibles.

**Le contrôle** : éprouver le motif sur un fichier **qui existe** (`ls -1 <dossier>/*.py | head -1`),
et compter ce que git voit vraiment : `git status --short --untracked-files=all | grep -c poc` doit valoir 0.

## 2. `git show --stat` compte le message du commit

`git show --stat --name-only HEAD | grep -c poc` a répondu **2** sur un commit qui
ne contenait aucun fichier de ce nom : les deux lignes trouvées étaient le message
du commit, celui qui parle justement du poc.

**Le contrôle** : compter les fichiers avec `git show --name-only --format="" HEAD`.

## 3. Un motif de lint ancré sur la disposition casse en silence

`ruff.toml` exemptait `E402` sur `"wazo_server/models/wazo_server_tenant.py"`.
Après le déplacement, le motif ne correspondait plus et la faute est **réapparue
sans que le fichier ait été touché**. Le piège vaut pour tout ce qui nomme un
chemin : config de lint, `per-file-ignores`, exclusions.

**Le contrôle** : écrire les motifs en `"**/"`, et rejouer le lint après tout
déplacement.

## 4. Un test qui clone `HEAD` n'éprouve pas l'arbre de travail

`tools/test_crochet.py` clone le dépôt : il éprouve le crochet **committé**. Un
outil corrigé mais non committé reste donc « en échec » à ses yeux — et neutraliser
une étape dans l'arbre de travail ne change rien à ce qu'il voit.

**Le contrôle** : committer avant de se fier à un vert. Pour prouver qu'un test
n'est pas complaisant, introduire la faute **dans un commit**, sur une branche
jetable, et exiger qu'il la nomme.

## 5. Un cas de test doit viser un endroit où la règle s'applique

Premier essai du cas « ligne trop longue » : 140 caractères ajoutés à un
`__manifest__.py`. Le crochet l'a laissée passer — non par faute, mais parce que la
config exempte `**/__manifest__.py` **et** `**/tests/*.py` d'`E501`.

**Le contrôle** : mesurer avant d'écrire le cas —
`printf '# %s\n' "$(printf 'x%.0s' $(seq 1 140))" | ruff check --stdin-filename <fichier> -`.

## 6. Un contrôle local qui n'a pas le périmètre de la CI produit un rouge après poussée

Le crochet lintait les modules ; la CI lintait aussi `tools/`. Une ligne trop
longue dans `tools/` est donc passée localement, et a rougi chez le coureur. Le
crochet lance maintenant **la même commande** que la CI, `addons` et `tools`.

**Le contrôle** : le crochet et la CI lancent la même commande, au même périmètre.

## 7. Un contrôle doit avouer sa cécité

Le travail « Qualité » de la CI ne clone pas Odoo. Le contrôle des imports
JavaScript y déclarait sept imports `@web/…` introuvables — dans un arbre absent.
Il dit désormais « Arbre Odoo absent : les imports JavaScript ne sont pas
vérifiés », et le contrôle des restes a été déplacé dans le travail qui clone.

**Le contrôle** : quand une dépendance manque, le dire — jamais crier au loup.

## 8. `curl` sans pot à témoins se rejoue à l'infini

`/web/login?db=odoo20` répondait 302 vers **la même adresse**, et j'en ai conclu
que le serveur ne servait plus la base. En réalité : deux appels `curl` distincts,
aucun cookie partagé — et ce serveur sert **deux** bases, donc la session décide.
Le serveur allait bien.

**Le contrôle** : `curl -c pot.txt …` puis `curl -b pot.txt …` ; le second appel
rend 200.

## Note d'exploitation — un verdict « cancelled » n'est ni un échec ni une preuve

Pousser un second commit annule l'exécution en cours du premier. Le verdict
« cancelled » veut dire **remplacée**, pas cassée — et il ne faut pas s'en
réjouir pour autant : il ne prouve rien. Ce qui compte est toujours le verdict de
la **dernière** exécution, celle qui porte le code qu'on croit avoir livré. Un
« Tests Odoo » annulé pendant que « Qualité » passe n'est pas une demi-réussite :
c'est une exécution qui n'a pas eu lieu.

## Note d'exploitation — la visibilité d'un dépôt ne se déduit pas de son usage

Trois affirmations de ce dépôt disaient « le dépôt est public ». Mesure :
`gh api repos/XtremXpert/hermes-odoo-addons --jq .visibility` répond `private`.
La règle qui en découlait — rien de secret dans un fichier suivi — reste bonne,
mais sa raison était fausse, et elle masquait une conséquence de sens contraire :
les minutes d'Actions d'un dépôt **privé** sont décomptées du forfait, celles d'un
dépôt public ne le sont pas. Une croyance confortable peut cacher un coût réel.
