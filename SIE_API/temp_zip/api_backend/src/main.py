import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, jsonify, render_template, send_from_directory
from flask_cors import CORS
from flask_mail import Mail
from src.models.user import db, User, WhatsAppInstance
from src.routes.auth import auth_bp, mail
from src.routes.whatsapp import whatsapp_bp
import os

app = Flask(__name__)
CORS(app)

# Configurações
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'sie_api_secret_key')
app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{os.getenv('DB_USERNAME', 'root')}:{os.getenv('DB_PASSWORD', 'password')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '3306')}/{os.getenv('DB_NAME', 'mydb')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configurações de e-mail
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@sieapi.com')

# Inicializar extensões
db.init_app(app)
mail.init_app(app)

# Registrar blueprints
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(whatsapp_bp, url_prefix='/api/whatsapp')

# Rota para servir arquivos estáticos
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

# Rota para verificar status da API
@app.route('/api/status')
def status():
    return jsonify({
        'status': 'online',
        'name': 'SIE API',
        'version': '1.0.0'
    })

# Criar tabelas do banco de dados
with app.app_context():
    db.create_all()
    
    # Criar usuário admin se não existir
    admin = User.query.filter_by(email='admin@sieapi.com').first()
    if not admin:
        admin = User(
            email='admin@sieapi.com',
            password='admin123',
            name='Administrador',
            is_admin=True
        )
        admin.confirm_email()  # Confirmar e-mail automaticamente
        db.session.add(admin)
        db.session.commit()
        print('Usuário admin criado com sucesso!')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
