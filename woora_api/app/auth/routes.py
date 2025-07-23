from flask import Blueprint, request, jsonify
from app.auth import services as auth_services

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    # Ajout d'un log pour inspecter les données reçues
    from flask import current_app
    current_app.logger.debug(f'Données reçues pour l\'inscription: {data}')
    email = data.get('email')

    password = data.get('password')
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    phone_number = data.get('phone_number')
    role = data.get('role')

    if not all([email, password, first_name, last_name, phone_number, role]):
        return jsonify({'message': 'Tous les champs sont requis.'}), 400

    try:
        user = auth_services.register_user(email, password, first_name, last_name, phone_number, role)
        return jsonify({'message': 'Inscription réussie. Un code de vérification a été envoyé à votre adresse e-mail.', 'user_id': user.id}), 201
    except ValueError as e:
        return jsonify({'message': str(e)}), 409 # Conflict
    except Exception as e:
        return jsonify({'message': 'Erreur interne du serveur.', 'error': str(e)}), 500

@auth_bp.route('/verify_email', methods=['POST'])
def verify_email():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')

    if not all([email, code]):
        return jsonify({'message': 'L\'e-mail et le code de vérification sont requis.'}), 400

    try:
        if auth_services.verify_email(email, code):
            return jsonify({'message': 'Adresse e-mail vérifiée avec succès. Vous pouvez maintenant vous connecter.'}), 200
        else:
            return jsonify({'message': 'Code de vérification ou e-mail invalide.'}), 400
    except Exception as e:
        return jsonify({'message': 'Erreur interne du serveur.', 'error': str(e)}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not all([email, password]):
        return jsonify({'message': 'L\'e-mail et le mot de passe sont requis.'}), 400

    try:
        user, access_token = auth_services.authenticate_user(email, password)
        return jsonify({
            'message': 'Connexion réussie.',
            'access_token': access_token,
            'user_role': user.role,
            'user_id': user.id
        }), 200
    except ValueError as e:
        return jsonify({'message': str(e)}), 401 # Unauthorized
    except Exception as e:
        return jsonify({'message': 'Erreur interne du serveur.', 'error': str(e)}), 500
