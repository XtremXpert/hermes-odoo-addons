def migrate(cr, version):
    """website makes ir.ui.view.visibility required (NOT NULL) without a
    database default. An update of this module is loaded before website, whose
    field is then missing from the registry: the new views are inserted with a
    NULL visibility and the update fails. Give the column the field's default.
    """
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'ir_ui_view'
           AND column_name = 'visibility'
           AND column_default IS NULL
        """
    )
    if cr.fetchone():
        cr.execute("ALTER TABLE ir_ui_view ALTER COLUMN visibility SET DEFAULT 'public'")
