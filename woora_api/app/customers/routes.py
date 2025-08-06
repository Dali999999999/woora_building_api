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

    total_amount = int(fee.amount * quantity)
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



# ---------- 2. WEBHOOK AMÉLIORÉ ----------
@customers_bp.route('/payment/webhook/fedapay', methods=['POST', 'GET'])
def fedapay_webhook():
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    # ========== LOGS DE SURVEILLANCE COMPLETS ==========
    print(f"🔥 [{timestamp}] ======= WEBHOOK FEDAPAY APPELÉ =======")
    print(f"🔥 Méthode: {request.method}")
    print(f"🔥 IP source: {request.remote_addr}")
    print(f"🔥 User-Agent: {request.headers.get('User-Agent', 'Non défini')}")
    print(f"🔥 URL complète: {request.url}")
    print(f"🔥 Content-Type: {request.headers.get('Content-Type', 'Non défini')}")
    print(f"🔥 Content-Length: {request.headers.get('Content-Length', 'Non défini')}")
    
    # Log de tous les headers importants
    important_headers = ['X-FEDAPAY-SIGNATURE', 'Authorization', 'X-Forwarded-For', 
                        'X-Real-IP', 'Host', 'Origin', 'Referer']
    for header in important_headers:
        value = request.headers.get(header)
        if value:
            print(f"🔥 {header}: {value}")
    
    # ========== GESTION DES REQUÊTES GET (TEST DE CONNECTIVITÉ) ==========
    if request.method == 'GET':
        print("✅ GET request sur webhook - Endpoint accessible")
        print(f"✅ URL configurée: {os.getenv('FEDAPAY_CALLBACK_URL', 'Non configurée')}")
        print(f"✅ Secret webhook configuré: {'Oui' if os.getenv('FEDAPAY_WEBHOOK_SECRET') else 'Non'}")
        return jsonify({
            'status': 'webhook_accessible',
            'timestamp': timestamp,
            'message': 'Endpoint webhook FedaPay fonctionnel'
        }), 200

    # ========== TRAITEMENT DES WEBHOOKS POST ==========
    try:
        # Récupération et log du payload
        payload = request.get_data()
        print(f"🔥 Taille du payload: {len(payload)} bytes")
        print(f"🔥 Payload brut: {payload}")
        
        if not payload:
            print("❌ Payload vide reçu")
            return jsonify({'status': 'empty_payload', 'timestamp': timestamp}), 400
        
        # Tentative de décodage du payload
        try:
            payload_str = payload.decode('utf-8')
            print(f"🔥 Payload décodé: {payload_str}")
        except UnicodeDecodeError as e:
            print(f"❌ Erreur décodage payload: {e}")
            return jsonify({'status': 'decode_error', 'timestamp': timestamp}), 400

        # ========== VÉRIFICATION DE LA SIGNATURE ==========
        provided_sig = request.headers.get('X-FEDAPAY-SIGNATURE')
        secret = os.getenv("FEDAPAY_WEBHOOK_SECRET")
        
        print(f"🔐 Signature fournie: {provided_sig}")
        print(f"🔐 Secret configuré: {'Oui (' + str(len(secret)) + ' chars)' if secret else 'Non'}")
        
        if not secret:
            print("⚠️  ATTENTION: Pas de secret webhook configuré - traitement sans vérification")
        elif not provided_sig:
            print("❌ Signature manquante dans les headers")
            print("❌ Headers reçus:", dict(request.headers))
            return jsonify({'status': 'missing_signature', 'timestamp': timestamp}), 401
        else:
            # Vérification de la signature
            expected_sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
            print(f"🔐 Signature attendue: {expected_sig}")
            
            try:
                # FedaPay peut envoyer la signature avec un préfixe
                if provided_sig.startswith('sha256='):
                    sig_part = provided_sig.replace('sha256=', '')
                elif '=' in provided_sig:
                    sig_part = provided_sig.split('=')[1]
                else:
                    sig_part = provided_sig
                    
                print(f"🔐 Signature extraite: {sig_part}")
                
                if not hmac.compare_digest(sig_part, expected_sig):
                    print("❌ Signature incorrecte")
                    print(f"❌ Attendu: {expected_sig}")
                    print(f"❌ Reçu: {sig_part}")
                    return jsonify({'status': 'invalid_signature', 'timestamp': timestamp}), 401
                else:
                    print("✅ Signature valide")
                    
            except (IndexError, ValueError) as e:
                print(f"❌ Format de signature invalide: {e}")
                return jsonify({'status': 'invalid_signature_format', 'timestamp': timestamp}), 401

        # ========== PARSING DES DONNÉES JSON ==========
        try:
            data = request.get_json()
            if not data:
                print("❌ Impossible de parser le JSON ou JSON vide")
                return jsonify({'status': 'invalid_json', 'timestamp': timestamp}), 400
                
            print(f"🔍 Données JSON reçues: {data}")
            
        except Exception as e:
            print(f"❌ Erreur parsing JSON: {e}")
            return jsonify({'status': 'json_error', 'details': str(e), 'timestamp': timestamp}), 400

        # ========== EXTRACTION DES INFORMATIONS TRANSACTION ==========
        # FedaPay peut envoyer différents formats
        transaction_data = data
        if 'v1/transaction' in data:
            transaction_data = data['v1/transaction']
            print("🔍 Structure imbriquée détectée")
        
        transaction_id = (transaction_data.get('id') or 
                         transaction_data.get('reference') or
                         str(data.get('id', '')))
        
        status = transaction_data.get('status', '').lower()
        amount = transaction_data.get('amount')
        
        print(f"🔍 ID Transaction: {transaction_id}")
        print(f"🔍 Statut: {status}")
        print(f"🔍 Montant: {amount}")
        
        if not transaction_id:
            print("❌ ID de transaction manquant")
            return jsonify({
                'status': 'missing_transaction_id', 
                'received_data': data,
                'timestamp': timestamp
            }), 400

        # ========== TRAITEMENT SELON LE STATUT ==========
        if status == 'approved':
            print(f"✅ Transaction approuvée: {transaction_id}")
            
            # Recherche de la transaction locale
            txn = Transaction.query.filter_by(related_entity_id=str(transaction_id)).first()
            if not txn:
                print(f"❌ Transaction locale {transaction_id} introuvable")
                
                # Log de toutes les transactions en attente pour debug
                pending_txns = Transaction.query.filter_by(description='En attente de validation').all()
                print(f"🔍 Transactions en attente: {[t.related_entity_id for t in pending_txns]}")
                
                return jsonify({
                    'status': 'transaction_not_found',
                    'transaction_id': transaction_id,
                    'timestamp': timestamp
                }), 404

            print(f"✅ Transaction locale trouvée: User {txn.user_id}, Montant {txn.amount}")
            
            # Vérification que la transaction n'est pas déjà traitée
            if 'validé' in txn.description:
                print(f"⚠️  Transaction {transaction_id} déjà traitée")
                return jsonify({
                    'status': 'already_processed',
                    'transaction_id': transaction_id,
                    'timestamp': timestamp
                }), 200

            # Récupération des données nécessaires
            user = User.query.get(txn.user_id)
            fee = ServiceFee.query.filter_by(service_key='visit_pass_purchase').first()
            
            if not user:
                print(f"❌ Utilisateur {txn.user_id} introuvable")
                return jsonify({
                    'status': 'user_not_found',
                    'user_id': txn.user_id,
                    'timestamp': timestamp
                }), 500
            
            if not fee:
                print("❌ ServiceFee 'visit_pass_purchase' introuvable")
                return jsonify({
                    'status': 'service_fee_not_found',
                    'timestamp': timestamp
                }), 500

            # Calcul et ajout des passes
            old_passes = user.visit_passes
            quantity = int(txn.amount / fee.amount)
            user.visit_passes += quantity
            txn.description = f'Achat de {quantity} passe(s) validé'
            
            try:
                db.session.commit()
                print(f"✅ Succès: +{quantity} passes ajoutés à l'utilisateur {user.id}")
                print(f"✅ Passes: {old_passes} -> {user.visit_passes}")
                print(f"✅ Transaction mise à jour: {txn.description}")
                
                return jsonify({
                    'status': 'success',
                    'transaction_id': transaction_id,
                    'user_id': user.id,
                    'passes_added': quantity,
                    'total_passes': user.visit_passes,
                    'timestamp': timestamp
                }), 200
                
            except Exception as e:
                db.session.rollback()
                print(f"❌ Erreur lors de la sauvegarde: {e}")
                return jsonify({
                    'status': 'database_error',
                    'error': str(e),
                    'timestamp': timestamp
                }), 500
                
        elif status in ['declined', 'canceled', 'failed']:
            print(f"❌ Transaction {status}: {transaction_id}")
            
            # Optionnel: mettre à jour la transaction locale
            txn = Transaction.query.filter_by(related_entity_id=str(transaction_id)).first()
            if txn and 'En attente' in txn.description:
                txn.description = f'Paiement {status}'
                try:
                    db.session.commit()
                    print(f"✅ Transaction {transaction_id} marquée comme {status}")
                except Exception as e:
                    print(f"⚠️  Erreur mise à jour transaction {status}: {e}")
            
            return jsonify({
                'status': 'payment_failed',
                'payment_status': status,
                'transaction_id': transaction_id,
                'timestamp': timestamp
            }), 200
            
        else:
            print(f"⚠️  Statut non géré: {status}")
            return jsonify({
                'status': 'unhandled_status',
                'payment_status': status,
                'transaction_id': transaction_id,
                'timestamp': timestamp
            }), 200

        return jsonify({
            'status': 'processed',
            'timestamp': timestamp
        }), 200

    except Exception as e:
        print(f"❌ Erreur critique webhook: {str(e)}")
        print(f"❌ Type d'erreur: {type(e).__name__}")
        import traceback
        print(f"❌ Traceback complet: {traceback.format_exc()}")
        
        return jsonify({
            'status': 'internal_error',
            'error': str(e),
            'error_type': type(e).__name__,
            'timestamp': timestamp
        }), 500


@customers_bp.route('/payment/cancel', methods=['GET'])
def payment_cancelled():
    """
    Gère l'annulation du paiement par l'utilisateur.
    """
    return jsonify({'status': 'cancelled', 'message': 'Paiement annulé par l’utilisateur'}), 200


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






