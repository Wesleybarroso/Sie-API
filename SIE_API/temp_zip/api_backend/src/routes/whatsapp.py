from flask import Blueprint, request, jsonify, current_app
from src.models.user import db, WhatsAppInstance, User
import requests
import json
from functools import wraps
import jwt
from datetime import datetime

whatsapp_bp = Blueprint('whatsapp', __name__)

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

# Configuração do serviço WhatsApp
WHATSAPP_SERVICE_URL = "http://localhost:3000/api"

# Criar nova instância
@whatsapp_bp.route('/instances', methods=['POST'])
@token_required
def create_instance(current_user):
    data = request.get_json()
    
    if not data or not data.get('name'):
        return jsonify({'message': 'Nome da instância não fornecido!'}), 400
    
    # Gerar ID de sessão único
    session_id = f"session_{current_user.id}_{datetime.utcnow().timestamp()}"
    
    # Criar instância no banco de dados
    new_instance = WhatsAppInstance(
        name=data['name'],
        session_id=session_id,
        instance_type=data.get('instance_type', 'whatsapp-web.js'),
        user_id=current_user.id,
        webhook_url=data.get('webhook_url'),
        ignore_groups=data.get('ignore_groups', False),
        block_calls=data.get('block_calls', False),
        prevent_message_deletion=data.get('prevent_message_deletion', False)
    )
    
    db.session.add(new_instance)
    db.session.commit()
    
    return jsonify({
        'message': 'Instância criada com sucesso!',
        'instance': new_instance.to_dict()
    }), 201

# Listar instâncias do usuário
@whatsapp_bp.route('/instances', methods=['GET'])
@token_required
def get_instances(current_user):
    # Administradores podem ver todas as instâncias
    if current_user.is_admin and request.args.get('all') == 'true':
        instances = WhatsAppInstance.query.all()
    else:
        instances = WhatsAppInstance.query.filter_by(user_id=current_user.id).all()
    
    return jsonify({
        'instances': [instance.to_dict() for instance in instances]
    }), 200

# Obter detalhes de uma instância
@whatsapp_bp.route('/instances/<int:instance_id>', methods=['GET'])
@token_required
def get_instance(current_user, instance_id):
    instance = WhatsAppInstance.query.get(instance_id)
    
    if not instance:
        return jsonify({'message': 'Instância não encontrada!'}), 404
    
    # Verificar permissão
    if instance.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'message': 'Permissão negada!'}), 403
    
    # Verificar status da instância no serviço WhatsApp
    try:
        response = requests.get(
            f"{WHATSAPP_SERVICE_URL}/status/{instance.session_id}",
            params={'type': instance.instance_type}
        )
        status_data = response.json()
        
        # Atualizar status de conexão
        if status_data.get('success'):
            instance.is_connected = status_data.get('status', {}).get('connected', False)
            db.session.commit()
    except:
        # Em caso de erro, não atualiza o status
        pass
    
    return jsonify({
        'instance': instance.to_dict()
    }), 200

# Atualizar instância
@whatsapp_bp.route('/instances/<int:instance_id>', methods=['PUT'])
@token_required
def update_instance(current_user, instance_id):
    instance = WhatsAppInstance.query.get(instance_id)
    
    if not instance:
        return jsonify({'message': 'Instância não encontrada!'}), 404
    
    # Verificar permissão
    if instance.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'message': 'Permissão negada!'}), 403
    
    data = request.get_json()
    
    if data.get('name'):
        instance.name = data['name']
    
    if 'webhook_url' in data:
        instance.webhook_url = data['webhook_url']
        
        # Atualizar webhook no serviço WhatsApp
        try:
            requests.post(
                f"{WHATSAPP_SERVICE_URL}/set-webhook",
                json={
                    'sessionId': instance.session_id,
                    'url': data['webhook_url'],
                    'ignoreGroups': instance.ignore_groups
                }
            )
        except:
            pass
    
    if 'ignore_groups' in data:
        instance.ignore_groups = data['ignore_groups']
    
    if 'block_calls' in data:
        instance.block_calls = data['block_calls']
    
    if 'prevent_message_deletion' in data:
        instance.prevent_message_deletion = data['prevent_message_deletion']
    
    if 'is_active' in data:
        instance.is_active = data['is_active']
    
    db.session.commit()
    
    return jsonify({
        'message': 'Instância atualizada com sucesso!',
        'instance': instance.to_dict()
    }), 200

# Excluir instância
@whatsapp_bp.route('/instances/<int:instance_id>', methods=['DELETE'])
@token_required
def delete_instance(current_user, instance_id):
    instance = WhatsAppInstance.query.get(instance_id)
    
    if not instance:
        return jsonify({'message': 'Instância não encontrada!'}), 404
    
    # Verificar permissão
    if instance.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'message': 'Permissão negada!'}), 403
    
    # Tentar fazer logout no serviço WhatsApp
    try:
        requests.post(
            f"{WHATSAPP_SERVICE_URL}/logout",
            json={'sessionId': instance.session_id}
        )
    except:
        pass
    
    db.session.delete(instance)
    db.session.commit()
    
    return jsonify({
        'message': 'Instância excluída com sucesso!'
    }), 200

# Iniciar instância (gerar QR code)
@whatsapp_bp.route('/instances/<int:instance_id>/init', methods=['POST'])
@token_required
def init_instance(current_user, instance_id):
    instance = WhatsAppInstance.query.get(instance_id)
    
    if not instance:
        return jsonify({'message': 'Instância não encontrada!'}), 404
    
    # Verificar permissão
    if instance.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'message': 'Permissão negada!'}), 403
    
    # Iniciar instância no serviço WhatsApp
    try:
        response = requests.post(
            f"{WHATSAPP_SERVICE_URL}/init",
            json={
                'sessionId': instance.session_id,
                'type': instance.instance_type
            }
        )
        
        if response.status_code == 200:
            return jsonify({
                'message': 'Instância iniciada com sucesso! Aguarde o QR code.'
            }), 200
        else:
            return jsonify({
                'message': 'Erro ao iniciar instância!',
                'error': response.json().get('error')
            }), 500
    except Exception as e:
        return jsonify({
            'message': 'Erro ao iniciar instância!',
            'error': str(e)
        }), 500

# Enviar mensagem
@whatsapp_bp.route('/instances/<int:instance_id>/send-message', methods=['POST'])
@token_required
def send_message(current_user, instance_id):
    instance = WhatsAppInstance.query.get(instance_id)
    
    if not instance:
        return jsonify({'message': 'Instância não encontrada!'}), 404
    
    # Verificar permissão
    if instance.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'message': 'Permissão negada!'}), 403
    
    data = request.get_json()
    
    if not data or not data.get('to') or not data.get('message'):
        return jsonify({'message': 'Destinatário ou mensagem não fornecidos!'}), 400
    
    # Enviar mensagem através do serviço WhatsApp
    try:
        response = requests.post(
            f"{WHATSAPP_SERVICE_URL}/send-message",
            json={
                'sessionId': instance.session_id,
                'to': data['to'],
                'message': data['message'],
                'type': instance.instance_type
            }
        )
        
        if response.status_code == 200:
            return jsonify({
                'message': 'Mensagem enviada com sucesso!'
            }), 200
        else:
            return jsonify({
                'message': 'Erro ao enviar mensagem!',
                'error': response.json().get('error')
            }), 500
    except Exception as e:
        return jsonify({
            'message': 'Erro ao enviar mensagem!',
            'error': str(e)
        }), 500

# Enviar mídia
@whatsapp_bp.route('/instances/<int:instance_id>/send-media', methods=['POST'])
@token_required
def send_media(current_user, instance_id):
    instance = WhatsAppInstance.query.get(instance_id)
    
    if not instance:
        return jsonify({'message': 'Instância não encontrada!'}), 404
    
    # Verificar permissão
    if instance.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'message': 'Permissão negada!'}), 403
    
    data = request.get_json()
    
    if not data or not data.get('to') or not data.get('mediaUrl') or not data.get('mediaType'):
        return jsonify({'message': 'Dados incompletos!'}), 400
    
    # Enviar mídia através do serviço WhatsApp
    try:
        response = requests.post(
            f"{WHATSAPP_SERVICE_URL}/send-media",
            json={
                'sessionId': instance.session_id,
                'to': data['to'],
                'mediaUrl': data['mediaUrl'],
                'caption': data.get('caption', ''),
                'mediaType': data['mediaType'],
                'type': instance.instance_type
            }
        )
        
        if response.status_code == 200:
            return jsonify({
                'message': 'Mídia enviada com sucesso!'
            }), 200
        else:
            return jsonify({
                'message': 'Erro ao enviar mídia!',
                'error': response.json().get('error')
            }), 500
    except Exception as e:
        return jsonify({
            'message': 'Erro ao enviar mídia!',
            'error': str(e)
        }), 500

# Mencionar todos em um grupo
@whatsapp_bp.route('/instances/<int:instance_id>/mention-all', methods=['POST'])
@token_required
def mention_all(current_user, instance_id):
    instance = WhatsAppInstance.query.get(instance_id)
    
    if not instance:
        return jsonify({'message': 'Instância não encontrada!'}), 404
    
    # Verificar permissão
    if instance.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'message': 'Permissão negada!'}), 403
    
    data = request.get_json()
    
    if not data or not data.get('groupId') or not data.get('message'):
        return jsonify({'message': 'ID do grupo ou mensagem não fornecidos!'}), 400
    
    # Mencionar todos através do serviço WhatsApp
    try:
        response = requests.post(
            f"{WHATSAPP_SERVICE_URL}/mention-all",
            json={
                'sessionId': instance.session_id,
                'groupId': data['groupId'],
                'message': data['message'],
                'anonymous': data.get('anonymous', False),
                'type': instance.instance_type
            }
        )
        
        if response.status_code == 200:
            return jsonify({
                'message': 'Menção enviada com sucesso!'
            }), 200
        else:
            return jsonify({
                'message': 'Erro ao mencionar todos!',
                'error': response.json().get('error')
            }), 500
    except Exception as e:
        return jsonify({
            'message': 'Erro ao mencionar todos!',
            'error': str(e)
        }), 500

# Obter contatos
@whatsapp_bp.route('/instances/<int:instance_id>/contacts', methods=['GET'])
@token_required
def get_contacts(current_user, instance_id):
    instance = WhatsAppInstance.query.get(instance_id)
    
    if not instance:
        return jsonify({'message': 'Instância não encontrada!'}), 404
    
    # Verificar permissão
    if instance.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'message': 'Permissão negada!'}), 403
    
    # Obter contatos através do serviço WhatsApp
    try:
        response = requests.get(
            f"{WHATSAPP_SERVICE_URL}/contacts/{instance.session_id}",
            params={'type': instance.instance_type}
        )
        
        if response.status_code == 200:
            return jsonify(response.json()), 200
        else:
            return jsonify({
                'message': 'Erro ao obter contatos!',
                'error': response.json().get('error')
            }), 500
    except Exception as e:
        return jsonify({
            'message': 'Erro ao obter contatos!',
            'error': str(e)
        }), 500

# Obter conversas
@whatsapp_bp.route('/instances/<int:instance_id>/chats', methods=['GET'])
@token_required
def get_chats(current_user, instance_id):
    instance = WhatsAppInstance.query.get(instance_id)
    
    if not instance:
        return jsonify({'message': 'Instância não encontrada!'}), 404
    
    # Verificar permissão
    if instance.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'message': 'Permissão negada!'}), 403
    
    # Obter conversas através do serviço WhatsApp
    try:
        response = requests.get(
            f"{WHATSAPP_SERVICE_URL}/chats/{instance.session_id}",
            params={'type': instance.instance_type}
        )
        
        if response.status_code == 200:
            return jsonify(response.json()), 200
        else:
            return jsonify({
                'message': 'Erro ao obter conversas!',
                'error': response.json().get('error')
            }), 500
    except Exception as e:
        return jsonify({
            'message': 'Erro ao obter conversas!',
            'error': str(e)
        }), 500

# Bloquear contato
@whatsapp_bp.route('/instances/<int:instance_id>/block-contact', methods=['POST'])
@token_required
def block_contact(current_user, instance_id):
    instance = WhatsAppInstance.query.get(instance_id)
    
    if not instance:
        return jsonify({'message': 'Instância não encontrada!'}), 404
    
    # Verificar permissão
    if instance.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'message': 'Permissão negada!'}), 403
    
    data = request.get_json()
    
    if not data or not data.get('contactId'):
        return jsonify({'message': 'ID do contato não fornecido!'}), 400
    
    # Bloquear contato através do serviço WhatsApp
    try:
        response = requests.post(
            f"{WHATSAPP_SERVICE_URL}/block-contact",
            json={
                'sessionId': instance.session_id,
                'contactId': data['contactId'],
                'type': instance.instance_type
            }
        )
        
        if response.status_code == 200:
            return jsonify({
                'message': 'Contato bloqueado com sucesso!'
            }), 200
        else:
            return jsonify({
                'message': 'Erro ao bloquear contato!',
                'error': response.json().get('error')
            }), 500
    except Exception as e:
        return jsonify({
            'message': 'Erro ao bloquear contato!',
            'error': str(e)
        }), 500

# Desbloquear contato
@whatsapp_bp.route('/instances/<int:instance_id>/unblock-contact', methods=['POST'])
@token_required
def unblock_contact(current_user, instance_id):
    instance = WhatsAppInstance.query.get(instance_id)
    
    if not instance:
        return jsonify({'message': 'Instância não encontrada!'}), 404
    
    # Verificar permissão
    if instance.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'message': 'Permissão negada!'}), 403
    
    data = request.get_json()
    
    if not data or not data.get('contactId'):
        return jsonify({'message': 'ID do contato não fornecido!'}), 400
    
    # Desbloquear contato através do serviço WhatsApp
    try:
        response = requests.post(
            f"{WHATSAPP_SERVICE_URL}/unblock-contact",
            json={
                'sessionId': instance.session_id,
                'contactId': data['contactId'],
                'type': instance.instance_type
            }
        )
        
        if response.status_code == 200:
            return jsonify({
                'message': 'Contato desbloqueado com sucesso!'
            }), 200
        else:
            return jsonify({
                'message': 'Erro ao desbloquear contato!',
                'error': response.json().get('error')
            }), 500
    except Exception as e:
        return jsonify({
            'message': 'Erro ao desbloquear contato!',
            'error': str(e)
        }), 500

# Configurar webhook para n8n
@whatsapp_bp.route('/instances/<int:instance_id>/set-webhook', methods=['POST'])
@token_required
def set_webhook(current_user, instance_id):
    instance = WhatsAppInstance.query.get(instance_id)
    
    if not instance:
        return jsonify({'message': 'Instância não encontrada!'}), 404
    
    # Verificar permissão
    if instance.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'message': 'Permissão negada!'}), 403
    
    data = request.get_json()
    
    if not data or not data.get('url'):
        return jsonify({'message': 'URL do webhook não fornecida!'}), 400
    
    # Atualizar no banco de dados
    instance.webhook_url = data['url']
    instance.ignore_groups = data.get('ignoreGroups', instance.ignore_groups)
    db.session.commit()
    
    # Configurar webhook através do serviço WhatsApp
    try:
        response = requests.post(
            f"{WHATSAPP_SERVICE_URL}/set-webhook",
            json={
                'sessionId': instance.session_id,
                'url': data['url'],
                'ignoreGroups': instance.ignore_groups
            }
        )
        
        if response.status_code == 200:
            return jsonify({
                'message': 'Webhook configurado com sucesso!'
            }), 200
        else:
            return jsonify({
                'message': 'Erro ao configurar webhook!',
                'error': response.json().get('error')
            }), 500
    except Exception as e:
        return jsonify({
            'message': 'Erro ao configurar webhook!',
            'error': str(e)
        }), 500
