Odoo 20 envoie les SMS par le service IAP d'Odoo : chaque message consomme un
crédit acheté, et le compte est lié à Odoo, pas au fournisseur téléphonique de
l'organisme. Diverse-Cité possède déjà un compte VoIP.ms dont des DID ont le
SMS activé, et le module `voipms_sms` y envoie des SMS depuis une boîte d'envoi
autonome.

Le besoin métier est de faire passer les SMS d'Odoo — ceux que les utilisateurs
envoient depuis le chatter, le CRM, les modèles de SMS et les campagnes — par ce
compte VoIP.ms, sans changer d'outil, sans toucher au cœur d'Odoo et sans
acheter de crédits IAP. Les réponses doivent revenir dans Odoo, au bon endroit,
et un STOP doit alimenter la liste noire d'Odoo.

Le module est donc un pont : il ne réimplémente ni le composeur, ni les modèles,
ni le suivi d'Odoo ; il remplace le transport (le fournisseur), par société, en
s'appuyant sur les mêmes points d'extension que `sms_twilio`, et ajoute
l'entrant par l'URL de rappel de VoIP.ms.
