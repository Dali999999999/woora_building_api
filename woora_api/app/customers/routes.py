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

    total_amount = int(fee.amount * quantity * 100)
    headers = {
        'Authorization': f'Bearer {os.getenv("FEDAPAY_SECRET_KEY")}',
        'Content-Type': 'application/json'
    }
    payload = {
        "description": f"Achat de {quantity} passe(s) de visite",
        "amount": total_amount,
        "currency": {"iso": "XOF"},
        "customer": {
            "firstname": user.first_name,
            "lastname": user.last_name,
            "email": user.email,
        },
        "callback_url": os.getenv("FEDAPAY_CALLBACK_URL", "https://woora-building-api.onrender.com/customers/payment/webhook/fedapay"),
        "cancel_url": os.getenv("FEDAPAY_CANCEL_URL", "https://woora-building-api.onrender.com/customers/payment/cancel")
    }

    try:
        # Ajout de logs pour debug
        print(f"🔍 Envoi requête FedaPay avec payload: {payload}")
        print(f"🔍 Headers: {headers}")
        
        resp = requests.post(
            "https://sandbox-api.fedapay.com/v1/transactions",
            json=payload,
            headers=headers,
            timeout=30  # Ajout d'un timeout
        )
        
        print(f"🔍 Statut FedaPay: {resp.status_code}")
        print(f"🔍 Réponse FedaPay: {resp.text}")
        
        # Vérification plus flexible du statut
        if resp.status_code not in [200, 201]:
            try:
                error_data = resp.json()
                return jsonify({
                    'error': 'Erreur FedaPay',
                    'details': error_data,
                    'status_code': resp.status_code
                }), 500
            except:
                return jsonify({
                    'error': 'Erreur FedaPay',
                    'details': resp.text or resp.reason,
                    'status_code': resp.status_code
                }), 500

        fp_data = resp.json()
        
        # Vérification de la structure de la réponse
        transaction_id = None
        checkout_url = None
        
        # FedaPay peut retourner différentes structures
        if 'v1/transaction' in fp_data:
            # Structure imbriquée
            transaction_data = fp_data['v1/transaction']
            transaction_id = transaction_data.get('id') or transaction_data.get('reference')
            # Chercher l'URL de checkout dans différents endroits possibles
            checkout_url = (transaction_data.get('payment_url') or
                          transaction_data.get('hosted_url') or 
                          transaction_data.get('checkout_url') or 
                          fp_data.get('payment_url') or
                          fp_data.get('hosted_url') or
                          fp_data.get('checkout_url'))
        else:
            # Structure directe
            transaction_id = fp_data.get('id') or fp_data.get('reference')
            checkout_url = (fp_data.get('payment_url') or
                          fp_data.get('hosted_url') or 
                          fp_data.get('checkout_url'))
        
        if not transaction_id:
            return jsonify({
                'error': 'ID de transaction manquant dans la réponse FedaPay',
                'response': fp_data
            }), 500
            
        if not checkout_url:
            return jsonify({
                'error': 'URL de checkout manquante dans la réponse FedaPay',
                'response': fp_data
            }), 500

        # Création de la transaction en base
        txn = Transaction(
            user_id=user.id,
            amount=fee.amount * quantity,
            type='payment',
            description='En attente de validation',
            related_entity_id=str(transaction_id)  # S'assurer que c'est une string
        )
        db.session.add(txn)
        db.session.commit()

        return jsonify({
            'message': 'Paiement initié avec succès.',
            'transaction_id': transaction_id,
            'quantity': quantity,
            'amount': float(fee.amount * quantity),
            'checkout_url': checkout_url
        }), 201

    except requests.exceptions.RequestException as e:
        return jsonify({
            'error': 'Erreur de connexion à FedaPay',
            'details': str(e)
        }), 500
    except Exception as e:
        return jsonify({
            'error': 'Erreur interne',
            'details': str(e)
        }), 500


# ---------- 2. WEBHOOK ----------
@customers_bp.route('/payment/webhook/fedapay', methods=['POST'])
def fedapay_webhook():
    try:
        payload = request.get_data()
        provided_sig = request.headers.get('X-FEDAPAY-SIGNATURE')

        secret = os.getenv("FEDAPAY_WEBHOOK_SECRET")
        if not secret or not provided_sig:
            return jsonify({'status': 'missing_sig'}), 401

        # Calculer la signature attendue
        expected_sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        # Extraire la signature depuis l'en-tête (format : t=...,s=...)
        try:
            sig_part = provided_sig.split('s=')[1]
        except IndexError:
            return jsonify({'status': 'invalid_sig_format'}), 401

        if not hmac.compare_digest(sig_part, expected_sig):
            return jsonify({'status': 'bad_signature'}), 401

        # Traiter l'événement
        data = request.get_json()
        print(f"🔍 Webhook reçu: {data}")
        
        if data.get('status') == 'approved':
            # Chercher la transaction par ID ou référence
            transaction_id = data.get('id') or data.get('reference')
            txn = Transaction.query.filter_by(related_entity_id=str(transaction_id)).first()
            
            if txn:
                user = User.query.get(txn.user_id)
                fee = ServiceFee.query.filter_by(service_key='visit_pass_purchase').first()
                
                if user and fee:
                    quantity = int(txn.amount / fee.amount)
                    user.visit_passes += quantity
                    txn.description = f'Achat de {quantity} passe(s) validé'
                    db.session.commit()
                    print(f"✅ Paiement validé pour l'utilisateur {user.id}: +{quantity} passes")
                else:
                    print(f"❌ Utilisateur ou fee introuvable pour la transaction {transaction_id}")
            else:
                print(f"❌ Transaction {transaction_id} introuvable en base")
                
        return jsonify({'status': 'ok'}), 200
        
    except Exception as e:
        print(f"❌ Erreur webhook: {str(e)}")
        return jsonify({'status': 'error', 'details': str(e)}), 500

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

