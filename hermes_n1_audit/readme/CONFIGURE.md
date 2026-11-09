Le module n'a pas de réglage dans Odoo : il s'active par un groupe.

1. Attribuer le groupe **Hermes N1 / modifications documentées**
   (`hermes_n1_audit.group_agent`) au compte de l'agent N1, dans l'onglet _Droits
   d'accès_ de sa fiche usager. C'est ce groupe qui autorise la façade ; il ne donne
   aucun droit administrateur.
2. Faire demander les modifications par un administrateur en conversation privée avec
   l'agent : la façade vérifie que le message source vient bien de lui, qu'il a moins
   d'une heure et que le canal est privé entre l'agent et le demandeur.
3. Le groupe peut lire l'historique `hermes.n1.change` ; l'écriture et la suppression
   y sont toujours refusées.
