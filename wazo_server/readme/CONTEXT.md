L'exploitant de la plateforme Wazo héberge plusieurs tenants. Un tenant neuf n'a
ni contexte ni utilisateur : créé seul dans Wazo, il est inutilisable, car
`wazo_phone` n'a nulle part où créer un poste. `wazo_server` fabrique le tenant
de bout en bout — tenant (wazo-auth), contexte interne et plages d'extensions
(wazo-confd), administrateur avec la politique d'administration, jeton d'API à
longue expiration — et remet ses coordonnées à l'exploitant du tenant.

La création est une séquence, pas un appel : chaque étape a son API, et un échec
en cours de route laisse des ressources distantes définitives. Le module la rend
donc reprenable et lisible : état, message d'erreur, identifiants distants
conservés, suppression refusée tant que le tenant porte des postes ou des
lignes. Un tenant déjà existant s'adopte : le listage de wazo-auth est cloisonné
par l'en-tête `Wazo-Tenant`, si bien qu'un parent est hors d'atteinte avec
l'en-tête de son enfant (`404 unknown-tenant`) ; l'adoption interroge donc
chaque tenant avec son propre en-tête et reprend son contexte réel. Les secrets
ne reviennent jamais du PBX : la fiche de remise les donne à ressaisir, et
*Renouveler le jeton* en fabrique un neuf puis révoque l'ancien.

Sur l'instance de l'exploitant, plusieurs tenants cohabitent : chaque fiche d'un
objet Wazo (utilisateur, groupe, file, IVR, conférence, parc, messagerie) choisit
son tenant, et l'en-tête comme le contexte envoyés en découlent ; sans choix, les
réglages s'appliquent — c'est ce qui permet à un tenant d'installer `wazo_phone`
seul. Le tableau de bord de l'exploitant croise les tenants, l'expiration de
leurs jetons (alerte à 30 jours) et l'état du pont VoIP.ms, le solde n'étant relu
que sur demande. Le module dépend de `wazo_tenant` et de `wazo_voipms`.

## Modèle de données

| Modèle | Champs clés | Relations |
| ------ | ----------- | --------- |
| `wazo.server.tenant` | name, slug, state, remote_uuid | « tenant parent » : → `wazo.server.tenant` (n-1) ; « objets rattachés » : ← les sept modèles ci-dessous (1-n) |
| `wazo.user` | name, extension, wazo_state | « tenant administré » : → `wazo.server.tenant` (n-1) |
| `wazo.ring.group` | name, extension, ring_strategy | « tenant administré » : → `wazo.server.tenant` (n-1) |
| `wazo.queue` | name, extension, wazo_state | « tenant administré » : → `wazo.server.tenant` (n-1) |
| `wazo.ivr` | name, menu_sound, timeout | « tenant administré » : → `wazo.server.tenant` (n-1) |
| `wazo.conference` | name, extension, pin | « tenant administré » : → `wazo.server.tenant` (n-1) |
| `wazo.parking` | name, extension, slots_start | « tenant administré » : → `wazo.server.tenant` (n-1) |
| `wazo.voicemail` | name, number, language | « tenant administré » : → `wazo.server.tenant` (n-1) |
