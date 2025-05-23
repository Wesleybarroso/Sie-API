from flask import Blueprint, request, jsonify, current_app
from src.models.user import db, User
import jwt
import datetime
import uuid
from functools import wraps
import os
from flask_mail import Mail, Message

auth_bp = Blueprint('auth', __name__)
mail = Mail()

# Decorator para verificar token JWT
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({'message': 'Token não fornecido!'}), 401
        
        try:
            data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.filter_by(id=data['user_id']).first()
            
            if not current_user:
                return jsonify({'message': 'Usuário não encontrado!'}), 401
                
            if not current_user.is_active:
                return jsonify({'message': 'Conta desativada!'}), 401
                
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token expirado!'}), 401
        except:
            return jsonify({'message': 'Token inválido!'}), 401
            
        return f(current_user, *args, **kwargs)
    
    return decorated

# Decorator para verificar se é admin
def admin_required(f):
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if not current_user.is_admin:
            return jsonify({'message': 'Permissão negada!'}), 403
        return f(current_user, *args, **kwargs)
    
    return decorated

# Função para enviar e-mail
def send_email(to, subject, template):
    msg = Message(
        subject,
        recipients=[to],
        html=template,
        sender=current_app.config['MAIL_DEFAULT_SENDER']
    )
    mail.send(msg)

# Rota de registro
@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    
    if not data or not data.get('email') or not data.get('password') or not data.get('name'):
        return jsonify({'message': 'Dados incompletos!'}), 400
    
    # Verificar se o e-mail já existe
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'message': 'E-mail já cadastrado!'}), 409
    
    # Criar novo usuário
    new_user = User(
        email=data['email'],
        password=data['password'],
        name=data['name']
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    # Enviar e-mail de confirmação
    confirmation_link = f"{request.host_url}api/auth/confirm/{new_user.confirmation_token}"
    template = f"""
    <h2>Bem-vindo à SIE API!</h2>
    <p>Olá {new_user.name},</p>
    <p>Obrigado por se cadastrar. Por favor, confirme seu e-mail clicando no link abaixo:</p>
    <p><a href="{confirmation_link}">Confirmar E-mail</a></p>
    <p>Se você não solicitou este cadastro, por favor ignore este e-mail.</p>
    <p>Atenciosamente,<br>Equipe SIE API</p>
    """
    
    try:
        send_email(new_user.email, "Confirme seu cadastro na SIE API", template)
        return jsonify({'message': 'Usuário cadastrado com sucesso! Verifique seu e-mail para confirmar o cadastro.'}), 201
    except Exception as e:
        return jsonify({'message': f'Usuário cadastrado, mas houve um erro ao enviar o e-mail: {str(e)}'}), 201

# Rota de confirmação de e-mail
@auth_bp.route('/confirm/<token>', methods=['GET'])
def confirm_email(token):
    user = User.query.filter_by(confirmation_token=token).first()
    
    if not user:
        return jsonify({'message': 'Link de confirmação inválido!'}), 404
    
    user.confirm_email()
    db.session.commit()
    
    # Redirecionar para a página de login
    return jsonify({'message': 'E-mail confirmado com sucesso! Você já pode fazer login.'}), 200

# Rota de login
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Dados incompletos!'}), 400
    
    user = User.query.filter_by(email=data['email']).first()
    
    if not user:
        return jsonify({'message': 'Usuário não encontrado!'}), 401
    
    if not user.check_password(data['password']):
        return jsonify({'message': 'Senha incorreta!'}), 401
    
    if not user.email_confirmed:
        return jsonify({'message': 'E-mail não confirmado! Verifique sua caixa de entrada.'}), 401
    
    if not user.is_active:
        return jsonify({'message': 'Conta desativada!'}), 401
    
    # Gerar token JWT
    token = jwt.encode({
        'user_id': user.id,
        'is_admin': user.is_admin,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=1)
    }, current_app.config['SECRET_KEY'], algorithm="HS256")
    
    return jsonify({
        'message': 'Login realizado com sucesso!',
        'token': token,
        'user': user.to_dict()
    }), 200

# Rota para solicitar recuperação de senha
@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    
    if not data or not data.get('email'):
        return jsonify({'message': 'E-mail não fornecido!'}), 400
    
    user = User.query.filter_by(email=data['email']).first()
    
    if not user:
        # Por segurança, não informamos se o e-mail existe ou não
        return jsonify({'message': 'Se o e-mail estiver cadastrado, você receberá um link para redefinir sua senha.'}), 200
    
    # Gerar token de recuperação
    reset_token = user.generate_reset_token()
    db.session.commit()
    
    # Enviar e-mail de recuperação
    reset_link = f"{request.host_url}api/auth/reset-password/{reset_token}"
    template = f"""
    <h2>Recuperação de Senha - SIE API</h2>
    <p>Olá {user.name},</p>
    <p>Você solicitou a recuperação de senha. Clique no link abaixo para redefinir sua senha:</p>
    <p><a href="{reset_link}">Redefinir Senha</a></p>
    <p>Este link expira em 24 horas.</p>
    <p>Se você não solicitou esta recuperação, por favor ignore este e-mail.</p>
    <p>Atenciosamente,<br>Equipe SIE API</p>
    """
    
    try:
        send_email(user.email, "Recuperação de Senha - SIE API", template)
    except Exception as e:
        return jsonify({'message': f'Erro ao enviar e-mail: {str(e)}'}), 500
    
    return jsonify({'message': 'Se o e-mail estiver cadastrado, você receberá um link para redefinir sua senha.'}), 200

# Rota para redefinir senha
@auth_bp.route('/reset-password/<token>', methods=['POST'])
def reset_password(token):
    data = request.get_json()
    
    if not data or not data.get('password'):
        return jsonify({'message': 'Nova senha não fornecida!'}), 400
    
    user = User.query.filter_by(reset_password_token=token).first()
    
    if not user:
        return jsonify({'message': 'Token inválido!'}), 404
    
    if user.reset_token_expires_at < datetime.datetime.utcnow():
        return jsonify({'message': 'Token expirado!'}), 401
    
    user.set_password(data['password'])
    user.reset_password_token = None
    user.reset_token_expires_at = None
    db.session.commit()
    
    return jsonify({'message': 'Senha redefinida com sucesso!'}), 200

# Rota para obter informações do usuário atual
@auth_bp.route('/me', methods=['GET'])
@token_required
def get_me(current_user):
    return jsonify({'user': current_user.to_dict()}), 200

# Rota para atualizar informações do usuário
@auth_bp.route('/update-profile', methods=['PUT'])
@token_required
def update_profile(current_user):
    data = request.get_json()
    
    if data.get('name'):
        current_user.name = data['name']
    
    if data.get('password'):
        current_user.set_password(data['password'])
    
    db.session.commit()
    
    return jsonify({'message': 'Perfil atualizado com sucesso!', 'user': current_user.to_dict()}), 200

# Rotas administrativas

# Listar todos os usuários (apenas admin)
@auth_bp.route('/users', methods=['GET'])
@token_required
@admin_required
def get_all_users(current_user):
    users = User.query.all()
    return jsonify({'users': [user.to_dict() for user in users]}), 200

# Criar usuário (apenas admin)
@auth_bp.route('/users', methods=['POST'])
@token_required
@admin_required
def create_user(current_user):
    data = request.get_json()
    
    if not data or not data.get('email') or not data.get('password') or not data.get('name'):
        return jsonify({'message': 'Dados incompletos!'}), 400
    
    # Verificar se o e-mail já existe
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'message': 'E-mail já cadastrado!'}), 409
    
    # Criar novo usuário
    new_user = User(
        email=data['email'],
        password=data['password'],
        name=data['name'],
        is_admin=data.get('is_admin', False)
    )
    
    # Se for criado por admin, já confirma o e-mail
    new_user.confirm_email()
    
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({'message': 'Usuário criado com sucesso!', 'user': new_user.to_dict()}), 201

# Atualizar usuário (apenas admin)
@auth_bp.route('/users/<int:user_id>', methods=['PUT'])
@token_required
@admin_required
def update_user(current_user, user_id):
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'message': 'Usuário não encontrado!'}), 404
    
    data = request.get_json()
    
    if data.get('name'):
        user.name = data['name']
    
    if data.get('email'):
        # Verificar se o e-mail já existe
        existing_user = User.query.filter_by(email=data['email']).first()
        if existing_user and existing_user.id != user_id:
            return jsonify({'message': 'E-mail já cadastrado!'}), 409
        user.email = data['email']
    
    if data.get('password'):
        user.set_password(data['password'])
    
    if 'is_admin' in data:
        user.is_admin = data['is_admin']
    
    if 'is_active' in data:
        user.is_active = data['is_active']
    
    db.session.commit()
    
    return jsonify({'message': 'Usuário atualizado com sucesso!', 'user': user.to_dict()}), 200

# Excluir usuário (apenas admin)
@auth_bp.route('/users/<int:user_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_user(current_user, user_id):
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'message': 'Usuário não encontrado!'}), 404
    
    # Não permitir excluir a si mesmo
    if user.id == current_user.id:
        return jsonify({'message': 'Não é possível excluir seu próprio usuário!'}), 403
    
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({'message': 'Usuário excluído com sucesso!'}), 200
