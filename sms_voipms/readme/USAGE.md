Envoyer un SMS comme d'habitude : composeur du chatter, action « Envoyer un
SMS », modèle de SMS, automatisation ou marketing de masse. Le message part par
VoIP.ms et le SMS passe à l'état *Envoyé* (accepté par le fournisseur).

Les identifiants renvoyés par VoIP.ms sont conservés sur le SMS et sur le suivi
(`sms.tracker`) ; ils restent visibles après le nettoyage des SMS envoyés.

Si VoIP.ms refuse l'envoi (numéro invalide, hors NANP, panne), le SMS passe à
l'état *Erreur* avec le motif du fournisseur ; il est possible de le renvoyer
depuis la liste des SMS. Aucun statut de livraison n'est fourni par VoIP.ms :
le SMS ne passe pas à *Livré*.

## Réponses

Une réponse est postée dans le chatter de l'enregistrement d'origine (le
dernier SMS envoyé à ce numéro, ≤ 90 jours), avec le contact en auteur s'il est
reconnu par son mobile. Sans envoi récent, elle va dans *SMS VoIP.ms →
Réponses entrantes* (état *Nouveau*), où on peut la marquer *Traité* ou
*Ignorée*.

Un **STOP** (STOP, ARRET, DÉSABONNER…) ajoute le numéro à la liste noire
téléphonique d'Odoo : les campagnes de masse l'excluent, les envois manuels
restent possibles, aucune confirmation n'est renvoyée.
