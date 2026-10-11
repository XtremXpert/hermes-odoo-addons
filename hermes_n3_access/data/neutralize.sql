-- Copie neutralisée (staging) : elle contient les données réelles des membres et
-- n'est pas ouverte aux agents. Le compte N3 copié de la production est désactivé
-- et ses clés API, valables sur la production, sont supprimées.
DELETE FROM res_users_apikeys
 WHERE user_id IN (SELECT id FROM res_users WHERE login = 'hermes_n3');
UPDATE res_users SET active = false WHERE login = 'hermes_n3';
