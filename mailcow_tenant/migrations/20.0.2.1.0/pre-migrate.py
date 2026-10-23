def migrate(cr, version):
    """Effacer les mots de passe que les versions précédentes gardaient en base.

    Le champ mailcow.mailbox.password et l'assistant mailcow.mailbox.password
    disparaissent. Odoo laisse en place la colonne d'un champ retiré et la
    table d'un modèle retiré : les valeurs y restaient. Elles sont effacées
    ici, sans être lues.
    """
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'mailcow_mailbox'
           AND column_name = 'password'
        """
    )
    if cr.fetchone():
        cr.execute("ALTER TABLE mailcow_mailbox DROP COLUMN password")
    cr.execute("DROP TABLE IF EXISTS mailcow_mailbox_password")
