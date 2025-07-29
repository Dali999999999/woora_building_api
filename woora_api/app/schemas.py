from marshmallow import Schema, fields

class VisitSettingsSchema(Schema):
    """
    Schéma pour la validation et la sérialisation des paramètres de visite.
    """
    initial_free_visit_passes = fields.Int(required=True, description="Nombre de pass de visite gratuits offerts à l'inscription.")
    visit_pass_price = fields.Decimal(places=2, required=True)

