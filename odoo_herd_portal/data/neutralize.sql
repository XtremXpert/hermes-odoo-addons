-- A neutralized copy (staging) must never drive the real clusters: no
-- instance creation, promotion, resync or sync from the copy.
UPDATE k8s_cluster SET active = false;

-- Staging operators (the CI, agents) drive stagings through the production's
-- Odoo: a copy keeps their accounts and API keys, which must not work there.
DELETE FROM res_users_apikeys
 WHERE user_id IN (
       SELECT rel.uid
         FROM res_groups_users_rel rel
         JOIN ir_model_data imd
           ON imd.model = 'res.groups'
          AND imd.res_id = rel.gid
        WHERE imd.module = 'odoo_herd_portal'
          AND imd.name = 'group_staging_operator'
);

UPDATE res_users
   SET active = false
 WHERE id IN (
       SELECT rel.uid
         FROM res_groups_users_rel rel
         JOIN ir_model_data imd
           ON imd.model = 'res.groups'
          AND imd.res_id = rel.gid
        WHERE imd.module = 'odoo_herd_portal'
          AND imd.name = 'group_staging_operator'
);
