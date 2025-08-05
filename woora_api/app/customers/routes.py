# woora_api/app/customers/routes.py

from flask import Blueprint, jsonify, request
from app.models import db, User, ServiceFee, Transaction
from flask_jwt_extended import jwt_required, get_jwt_identity

# Blueprint pour les routes accessibles uniquement aux customers
customers_bp = Blueprint('customers', __name__, url_prefix='/customers')


# --------------------------------------------
# Route pour initier l'achat de passes de visite
# --------------------------------------------
@customers_bp.route('/payment/initiate_visit_pass', methods=['POST'])
@jwt_required()
def initiate_visit_pass_payment():
    """
    Permet à un utilisateur authentifié avec le rôle 'customer'
    d'initier un paiement pour acheter des passes de visite.
    """
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)

    # Vérification stricte : seul un customer peut passer cette commande
    if user.role != 'customer':
        return jsonify({'error': 'Accès refusé : rôle customer requis.'}), 403

    data = request.get_json() or {}
    quantity = data.get('quantity', 1)

    if not isinstance(quantity, int) or quantity < 1:
        return jsonify({'error': 'Quantité invalide.'}), 400

    # Récupération du prix unitaire configuré par l'admin
    fee = ServiceFee.query.filter_by(service_key='visit_pass_purchase').first()
    if not fee:
        return jsonify({'error': 'Prix du pass non défini.'}), 500

    total_amount = fee.amount * quantity

    # Ici on crée la transaction en base (statut "pending")
    txn = Transaction(
        user_id=user.id,
        amount=total_amount,
        type='payment',
        description=f'Achat de {quantity} passe(s) – en attente de validation',
        related_entity_id=None  # sera renseigné après le webhook Fedapay
    )
    db.session.add(txn)
    db.session.commit()

    # (Optionnel) Ici tu intégreras l’appel à l’API Fedapay pour obtenir l’URL de paiement
    # Pour l’instant on retourne un succès factice
    return jsonify({
        'message': 'Paiement initié avec succès.',
        'transaction_id': txn.id,
        'quantity': quantity,
        'amount': float(total_amount),
        'checkout_url': fp_data['hosted_url']
    }), 201


# --------------------------------------------
# Webhook sécurisé appelé par Fedapay
# --------------------------------------------
@customers_bp.route('/payment/webhook/fedapay', methods=['POST'])
def fedapay_webhook():
    """
    Reçoit les événements de paiement de Fedapay.
    Si le statut est 'approved', on crédite les passes à l’utilisateur.
    """
    payload = request.get_json() or {}
    status = payload.get('status')
    fedapay_transaction_id = payload.get('id')

    # (Facultatif) Vérifier la signature Fedapay ici pour plus de sécurité

    if status != 'approved':
        return jsonify({'status': 'ignored'}), 200

    # Récupérer la transaction interne correspondante
    txn = Transaction.query.filter_by(
        description=f'Achat – Fedapay transaction {fedapay_transaction_id}'
    ).first()

    # Si aucune transaction locale, on ignore
    if not txn:
        return jsonify({'status': 'not_found'}), 200

    user = User.query.get(txn.user_id)
    if not user or user.role != 'customer':
        return jsonify({'status': 'invalid_user'}), 200

    # Calcul du nombre de passes achetées
    fee = ServiceFee.query.filter_by(service_key='visit_pass_purchase').first()
    if not fee or fee.amount <= 0:
        return jsonify({'status': 'invalid_price'}), 200

    quantity = int(txn.amount / fee.amount)

    # On ajoute les passes au compte de l’utilisateur
    user.visit_passes += quantity
    txn.description = f'Achat de {quantity} passe(s) validé'
    db.session.commit()

    return jsonify({'status': 'ok'}), 200


# --------------------------------------------
# Routes existantes déjà présentes (non modifiées)
# --------------------------------------------
@customers_bp.route('/properties', methods=['GET'])
@jwt_required()
def get_all_properties_for_customer():
    """
    Endpoint pour les customers.
    Récupère tous les biens immobiliers.
    Accessible uniquement par les customers authentifiés.
    """
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)

    if user.role != 'customer':
        return jsonify({'message': 'Accès refusé : rôle customer requis.'}), 403

    properties = Property.query.all()
    return jsonify([p.to_dict() for p in properties]), 200


@customers_bp.route('/properties/<int:property_id>', methods=['GET'])
@jwt_required()
def get_property_details_for_customer(property_id):
    """
    Endpoint pour les customers.
    Récupère les détails d'un bien immobilier spécifique.
    """
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)

    if user.role != 'customer':
        return jsonify({'message': 'Accès refusé : rôle customer requis.'}), 403

    property = Property.query.get(property_id)
    if not property:
        return jsonify({'message': "Bien immobilier non trouvé."}), 404

    return jsonify(property.to_dict()), 200

