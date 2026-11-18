Envoyer un SMS comme d'habitude : composeur du chatter, action « Envoyer un
SMS », modèle de SMS, automatisation ou marketing de masse. Le message part par
VoIP.ms et le SMS passe à l'état *Envoyé* (en attente de livraison chez
VoIP.ms), puis à *Livré* lorsque le fournisseur le confirme.

Les identifiants renvoyés par VoIP.ms sont conservés sur le suivi
(`sms.tracker`) et restent visibles sur la fiche du SMS, même après le
nettoyage des SMS envoyés.

Si VoIP.ms refuse l'envoi (numéro invalide, hors NANP, crédit épuisé, panne),
le SMS passe à l'état *Erreur* avec le motif du fournisseur ; il est possible de
le renvoyer depuis la liste des SMS.
