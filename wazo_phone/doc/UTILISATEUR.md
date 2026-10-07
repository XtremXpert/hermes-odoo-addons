# Guide utilisateur — Téléphonie Wazo

Vous êtes **utilisateur** du module **Téléphonie Wazo** (rôle _Téléphonie Wazo :
Utilisateur_). Ce module relie votre poste **Wazo** à votre fiche **Odoo** : vous
consultez vos appels dans Odoo et, si l'administrateur a activé le **softphone**, vous
**passez vos appels** directement depuis le navigateur.

> Ce que vous voyez dépend de votre rôle. Les réglages de connexion et la
> création/suppression de postes relèvent du **gestionnaire** (voir le guide
> administrateur).

---

## 1. Ce que vous pouvez faire

- Consulter le **journal d'appels** (menu **Téléphonie Wazo → Journal d'appels**).
- Voir votre **poste Wazo** et votre **utilisateur Wazo** sur votre **fiche Contact**.
- Parcourir les **appels** associés à chaque contact.
- (Si le softphone est actif) **appeler/répondre** depuis le navigateur.

Vous disposez d'un **accès en lecture** : vous ne créez ni ne supprimez de postes.

---

## 2. Mon poste et mon utilisateur Wazo

Ouvrez votre **fiche Contact**, onglet **Téléphonie Wazo** :

- **Poste Wazo** : votre numéro interne (ex : `1005`).
- **Utilisateur Wazo** : le bouton **Ouvrir** affiche votre fiche utilisateur (état de
  synchronisation, identifiant SIP).

> Le poste est dérivé du champ **Téléphone** de votre contact au moment de la création
> par l'administrateur.

---

## 3. Journal d'appels

**Téléphonie Wazo → Journal d'appels** affiche la liste des appels :

| Colonne     | Signification                                                                               |
| ----------- | ------------------------------------------------------------------------------------------- |
| Début       | date/heure de début de l'appel                                                              |
| Sens        | **Sortant** (vous avez appelé), **Entrant** (on vous a appelé), **Interne** (poste ↔ poste) |
| Appelant    | numéro (poste) et nom de l'appelant                                                         |
| Destination | numéro (poste) et nom du destinataire                                                       |
| Répondu     | l'appel a-t-il été pris ?                                                                   |
| Durée (s)   | durée de la communication (somme en bas de liste)                                           |
| Contact     | le contact Odoo identifié pour cet appel                                                    |

### Lire un appel

Cliquez sur une ligne pour ouvrir le détail : dates de début/fin, sens, parties
(appelant / destination), contact associé.

### Identifier un contact

Odoo associe automatiquement chaque appel à un **Contact** quand c'est possible :

- d'abord par le **poste Wazo** du contact ;
- sinon par le **numéro de téléphone** du contact (le formatage — espaces, tirets,
  points — est ignoré).

Si aucun contact ne correspond, la colonne Contact reste vide (l'appel est néanmoins
comptabilisé).

### Filtrer

- Dans la **liste**, utilisez la recherche/filtres (sens, période, contact).
- Sur une **fiche Contact**, le bouton **Voir les appels** (onglet Téléphonie Wazo)
  ouvre uniquement les appels de ce contact.

> Le journal est **alimenté par la synchronisation** (manuel ou planifiée, gérée par
> l'administrateur). Il n'est pas temps réel.

---

## 4. Softphone (si activé)

L'administrateur peut activer le **softphone WebRTC** (pont vers le module « voip »
d'Odoo Enterprise). S'il est actif, votre poste Wazo devient utilisable **directement
dans le navigateur** :

- un **cliquable téléphone** apparaît dans l'interface Odoo ;
- vous **appelez** en cliquant sur un poste/numéro ;
- vous **répondez** aux appels entrants ;
- la communication passe en **WebRTC** (chiffrement DTLS, codecs du navigateur), via le
  point d'accès WebSocket de Wazo.

### Conditions

- Le module « voip » d'Enterprise doit être installé et le pont activé.
- Votre utilisateur Odoo doit avoir reçu vos **identifiants SIP** (propagation
  automatique par l'administrateur).

> Si le softphone n'est pas disponible, vous utilisez votre **poste SIP classique**
> (identifiant = poste, mot de passe SIP fourni par le gestionnaire).

---

## 5. Rappels et limites

- **Lecture seule** : vous ne modifiez pas les postes ni la configuration.
- **Journal non temps réel** : il se met à jour à la synchronisation.
- **Contact vide** : un appel sans correspondance de contact reste listé, la colonne
  Contact étant vide.
- **Confidentialité** : le mot de passe SIP n'est visible que des gestionnaires.

En cas de souci (poste non synchronisé, appel non listé, softphone inactif),
reportez-vous à votre **administrateur**.
