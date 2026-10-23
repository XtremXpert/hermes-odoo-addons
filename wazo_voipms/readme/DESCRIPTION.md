Pont entre **Wazo** (PBX, module ``wazo_phone``) et **VoIP.ms** (trunk RTC,
module ``voipms_sms``).

Deux directions :

* **Sortant** — ``wazo.voipms.trunk`` provisionne un sous-compte SIP chez
  VoIP.ms, un endpoint+trunk+outcall côté Wazo. Les usagers composent
  ``<préfixe><numéro>`` pour sortir par ce trunk.
* **Entrant** — un DID VoIP.ms (``voipms.did``) peut être routé vers une
  destination Wazo (utilisateur ou groupe d'appel) : le module crée
  l'``incall`` dans ``from-extern`` puis bascule le routage VoIP.ms en
  ``sip:<DID>@<hôte Wazo>``.
