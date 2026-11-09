Ce module n'a pas d'impact sur l'interface utilisateur : il n'ajoute ni menu ni vue.
La façade s'appelle en RPC par le compte agent N1 et n'accorde aucun droit
supplémentaire : chaque écriture passe par les droits ORM du demandeur authentifié.

Chaque mutation laisse une note dans le chatter de l'objet, ou dans le journal
`hermes.n1.change` pour les objets sans chatter et les suppressions. Ce journal est
immuable et n'a pas d'écran : il ne se lit que par RPC.
