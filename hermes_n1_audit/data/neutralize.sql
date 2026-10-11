-- Neutralized copies (stagings, odoo neutralize): Hermes agents must not run
-- against them. Every account holding a group of a hermes_* module is
-- deactivated and loses its API keys, so a copy can never be driven by an
-- agent, even with keys cloned from production. Explicit memberships only:
-- agent groups are always assigned directly.
DELETE FROM res_users_apikeys
 WHERE user_id IN (
       SELECT rel.uid
         FROM res_groups_users_rel rel
         JOIN ir_model_data imd
           ON imd.model = 'res.groups'
          AND imd.res_id = rel.gid
        WHERE imd.module LIKE 'hermes\_%'
);

UPDATE res_users
   SET active = false
 WHERE id IN (
       SELECT rel.uid
         FROM res_groups_users_rel rel
         JOIN ir_model_data imd
           ON imd.model = 'res.groups'
          AND imd.res_id = rel.gid
        WHERE imd.module LIKE 'hermes\_%'
);
