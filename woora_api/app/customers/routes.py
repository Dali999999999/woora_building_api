# woora_api/app/customers/routes.py
import os
import hmac
import hashlib
import requests
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, User, ServiceFee, Transaction

customers_bp = Blueprint('customers', __name__, url_prefix='/customers')

# ---------- 1. INITIER LE PAIEMENT ----------
@customers_bp.route('/payment/initiate_visit_pass', methods=['POST'])
@jwt_required()
def initiate_visit_pass_payment():
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    if user.role != 'customer':
        return jsonify({'error': 'Accès refusé : rôle customer requis.'}), 403

    data = request.get_json() or {}
    quantity = data.get('quantity', 1)
    if not isinstance(quantity, int) or quantity < 1:
        return jsonify({'error': 'Quantité invalide.'}), 400

    fee = ServiceFee.query.filter_by(service_key='visit_pass_purchase').first()
    if not fee:
        return jsonify({'error': 'Prix du pass non défini.'}), 500

    total_amount = int(fee.amount * 100)  # centimes
    headers = {
        'Authorization': f'Bearer {os.getenv("FEDAPAY_SECRET_KEY")}',
        'Content-Type': 'application/json'
    }
    payload = {
        "description": f"Achat de {quantity} passe(s) de visite",
        "amount": total_amount,
        "currency": "XOF",
        "customer": {
            "firstname": user.first_name,
            "lastname": user.last_name,
            "email": user.email,
            "phone_number": {"number": user.phone_number, "country": "SN"}
        },
        "callback_url": None,
        "cancel_url": None
    }

    resp = requests.post(
        "https://sandbox-api.fedapay.com/v1/transactions",
        json=payload,
        headers=headers
    )
    if resp.status_code != 201:
        return jsonify({
            'error': 'Erreur FedaPay',
            'details': resp.text or resp.reason,
            'status_code': resp.status_code
        }), 500
    fp_data = resp.json()
    txn = Transaction(
        user_id=user.id,
        amount=fee.amount * quantity,
        type='payment',
        description='En attente de validation',
        related_entity_id=fp_data['id']
    )
    db.session.add(txn)
    db.session.commit()

    return jsonify({
        'message': 'Paiement initié avec succès.',
        'transaction_id': fp_data['id'],
        'quantity': quantity,
        'amount': float(fee.amount * quantity),
        'checkout_url': fp_data['hosted_url']
    }), 201


# ---------- 2. WEBHOOK ----------
@customers_bp.route('/payment/webhook/fedapay', methods=['POST'])
def fedapay_webhook():
    payload = request.get_data()
    sig_header = request.headers.get('FedaPay-Signature')
    secret = os.getenv("FEDAPAY_WEBHOOK_SECRET")

    if not sig_header or not hmac.compare_digest(
        hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest(),
        sig_header
    ):
        return jsonify({'status': 'bad_signature'}), 401

    data = request.get_json()
    status = data.get('status')
    fp_id = data.get('id')

    if status != 'approved':
        return jsonify({'status': 'ignored'}), 200

    txn = Transaction.query.filter_by(related_entity_id=fp_id).first()
    if not txn:
        return jsonify({'status': 'not_found'}), 200

    user = User.query.get(txn.user_id)
    if not user or user.role != 'customer':
        return jsonify({'status': 'invalid_user'}), 200

    fee = ServiceFee.query.filter_by(service_key='visit_pass_purchase').first()
    if not fee or fee.amount <= 0:
        return jsonify({'status': 'invalid_price'}), 200

    quantity = int(txn.amount / fee.amount)
    user.visit_passes += quantity
    txn.description = f'Achat de {quantity} passe(s) validé'
    db.session.commit()
    return jsonify({'status': 'ok'}), 200

# ---------- 3. Routes existantes ----------
@customers_bp.route('/properties', methods=['GET'])
@jwt_required()
def get_all_properties_for_customer():
    user_id = get_jwt_identity()
    if User.query.get(user_id).role != 'customer':
        return jsonify({'message': 'Accès refusé : customer requis.'}), 403
    from app.models import Property
    return jsonify([p.to_dict() for p in Property.query.all()]), 200

@customers_bp.route('/properties/<int:property_id>', methods=['GET'])
@jwt_required()
def get_property_details_for_customer(property_id):
    user_id = get_jwt_identity()
    if User.query.get(user_id).role != 'customer':
        return jsonify({'message': 'Accès refusé : customer requis.'}), 403
    from app.models import Property
    prop = Property.query.get_or_404(property_id)
    return jsonify(prop.to_dict()), 200




