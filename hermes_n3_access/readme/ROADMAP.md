Le module ne crée ni mot de passe ni clé API : sans intervention humaine, le
compte `hermes_n3` ne peut pas s'authentifier. La création de la clé et son
rangement dans le coffre restent des gestes manuels, documentés dans
Configuration.

Le compte est limité à `base.group_user` et `base.group_partner_manager` ; tout
ce qui demande des droits d'administration doit passer par les outils N3, pas
par ce compte. C'est voulu, mais cela veut dire que l'agent ne peut pas
administrer Odoo lui-même.

Sur une copie neutralisée, les clés du compte sont supprimées et le compte est
désactivé. Pour le réactiver, il faut réactiver le compte puis créer une
nouvelle clé : l'ancienne n'est pas restaurée. Le module ne pose ni menu ni vue ;
son effet n'est visible que dans la liste des utilisateurs.
