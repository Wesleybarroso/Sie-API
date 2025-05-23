# Documentação de Instalação e Uso - SIE API

## Visão Geral

SIE API é uma solução completa para integração com WhatsApp, permitindo a automação de mensagens, gerenciamento de múltiplas instâncias e integração com plataformas de automação como o n8n.

## Requisitos do Sistema

- Node.js 14+ (recomendado 16+)
- Python 3.8+
- MySQL 5.7+ ou MariaDB 10.5+
- Servidor web (Nginx ou Apache)
- Suporte a HTTPS (obrigatório para produção)

## Estrutura do Projeto

O projeto é dividido em duas partes principais:

1. **API Backend (Flask)**: Gerencia autenticação, usuários e instâncias
2. **Serviço WhatsApp (Node.js)**: Gerencia conexões com WhatsApp e processamento de mensagens

## Instalação no CloudPanel

### 1. Preparação do Ambiente

1. Faça login no seu CloudPanel
2. Crie um novo site (por exemplo, `sieapi.seudominio.com`)
3. Selecione PHP como tipo de aplicação (vamos substituir depois)
4. Ative o SSL para o domínio

### 2. Configuração do Banco de Dados

1. No CloudPanel, vá para "Databases" e crie um novo banco de dados MySQL
2. Anote o nome do banco, usuário e senha

### 3. Upload e Extração dos Arquivos

1. Faça upload do arquivo .zip para o servidor usando SFTP
2. Conecte-se via SSH ao servidor
3. Navegue até o diretório do site: `cd /home/cloudpanel/htdocs/seudominio.com`
4. Extraia o arquivo: `unzip arquivo.zip`

### 4. Configuração do Backend Flask

1. Navegue até o diretório do backend: `cd /home/cloudpanel/htdocs/seudominio.com/SIE_API/api_backend`
2. Crie um ambiente virtual: `python3 -m venv venv`
3. Ative o ambiente virtual: `source venv/bin/activate`
4. Instale as dependências: `pip install -r requirements.txt`
5. Configure as variáveis de ambiente:

```bash
cat > .env << EOF
SECRET_KEY=sua_chave_secreta_aqui
DB_USERNAME=seu_usuario_mysql
DB_PASSWORD=sua_senha_mysql
DB_HOST=localhost
DB_PORT=3306
DB_NAME=seu_banco_mysql
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=seu_email@gmail.com
MAIL_PASSWORD=sua_senha_app_gmail
MAIL_DEFAULT_SENDER=noreply@seudominio.com
EOF
```

### 5. Configuração do Serviço WhatsApp

1. Navegue até o diretório do serviço WhatsApp: `cd /home/cloudpanel/htdocs/seudominio.com/SIE_API/whatsapp_service`
2. Instale as dependências: `npm install`
3. Configure as variáveis de ambiente:

```bash
cat > .env << EOF
PORT=3000
EOF
```

### 6. Configuração do Supervisor para Manter os Serviços Rodando

1. Instale o supervisor se ainda não estiver instalado: `apt-get install supervisor`
2. Crie a configuração para o backend Flask:

```bash
cat > /etc/supervisor/conf.d/sieapi_backend.conf << EOF
[program:sieapi_backend]
directory=/home/cloudpanel/htdocs/seudominio.com/SIE_API/api_backend
command=/home/cloudpanel/htdocs/seudominio.com/SIE_API/api_backend/venv/bin/python src/main.py
autostart=true
autorestart=true
stderr_logfile=/var/log/sieapi_backend.err.log
stdout_logfile=/var/log/sieapi_backend.out.log
user=cloudpanel
EOF
```

3. Crie a configuração para o serviço WhatsApp:

```bash
cat > /etc/supervisor/conf.d/sieapi_whatsapp.conf << EOF
[program:sieapi_whatsapp]
directory=/home/cloudpanel/htdocs/seudominio.com/SIE_API/whatsapp_service
command=node index.js
autostart=true
autorestart=true
stderr_logfile=/var/log/sieapi_whatsapp.err.log
stdout_logfile=/var/log/sieapi_whatsapp.out.log
user=cloudpanel
EOF
```

4. Recarregue o supervisor:

```bash
supervisorctl reread
supervisorctl update
```

### 7. Configuração do Nginx como Proxy Reverso

1. No CloudPanel, vá para "Sites" e selecione seu site
2. Clique em "Vhost" e substitua a configuração pelo seguinte:

```nginx
server {
    listen 80;
    server_name sieapi.seudominio.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name sieapi.seudominio.com;

    # SSL
    ssl_certificate /etc/letsencrypt/live/sieapi.seudominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/sieapi.seudominio.com/privkey.pem;
    
    # Proxy para o backend Flask
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Proxy para o serviço WhatsApp
    location /api/whatsapp-service/ {
        proxy_pass http://127.0.0.1:3000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Configuração para WebSockets
    location /socket.io/ {
        proxy_pass http://127.0.0.1:3000/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

3. Salve a configuração e reinicie o Nginx: `service nginx restart`

## Uso do Sistema

### Acesso ao Painel

1. Acesse `https://sieapi.seudominio.com` no navegador
2. Faça login com as credenciais padrão:
   - E-mail: `admin@sieapi.com`
   - Senha: `admin123`
3. **IMPORTANTE**: Altere a senha padrão imediatamente após o primeiro login

### Criação de Instâncias WhatsApp

1. No painel, clique em "Nova Instância"
2. Preencha o nome da instância e selecione o tipo (WhatsApp Web.js ou Baileys)
3. Configure as opções desejadas (webhook para n8n, ignorar grupos, etc.)
4. Clique em "Criar Instância"
5. Para conectar, clique no botão "Conectar" da instância criada
6. Escaneie o QR code com seu WhatsApp

### Integração com n8n

1. No n8n, crie um novo workflow
2. Adicione um nó "Webhook" para receber notificações da SIE API
3. Copie a URL do webhook
4. No painel da SIE API, edite a instância e cole a URL do webhook
5. Para enviar mensagens do n8n para a SIE API, use um nó "HTTP Request" com:
   - Método: POST
   - URL: `https://sieapi.seudominio.com/api/whatsapp/instances/{ID_DA_INSTANCIA}/send-message`
   - Headers: `Authorization: Bearer {SEU_TOKEN}`
   - Body: `{"to": "5511999999999@c.us", "message": "Sua mensagem"}`

## Funcionalidades Principais

- **Múltiplas Instâncias**: Gerencie vários números de WhatsApp simultaneamente
- **Envio de Mensagens**: Texto, áudio, imagens e documentos
- **Marcação em Grupo**: Marque todos os participantes de um grupo, incluindo modo anônimo
- **Bloqueio de Ligações**: Evite receber chamadas
- **Anti-Apagamento**: Impede que mensagens recebidas sejam apagadas
- **Integração n8n**: Automatize fluxos de mensagens com webhooks
- **Gerenciamento de Usuários**: Controle quem pode acessar o sistema

## Solução de Problemas

### Verificando Logs

- Backend Flask: `tail -f /var/log/sieapi_backend.out.log`
- Serviço WhatsApp: `tail -f /var/log/sieapi_whatsapp.out.log`
- Erros do Backend: `tail -f /var/log/sieapi_backend.err.log`
- Erros do WhatsApp: `tail -f /var/log/sieapi_whatsapp.err.log`

### Problemas Comuns

1. **QR Code não aparece**:
   - Verifique se o serviço WhatsApp está rodando: `supervisorctl status sieapi_whatsapp`
   - Reinicie o serviço: `supervisorctl restart sieapi_whatsapp`

2. **Erro de conexão com banco de dados**:
   - Verifique as credenciais no arquivo .env
   - Confirme se o banco de dados está acessível: `mysql -u usuario -p`

3. **Webhook não funciona**:
   - Verifique se a URL está correta e acessível publicamente
   - Confirme se o n8n está configurado para receber webhooks

## Considerações de Segurança

- Altere a senha do administrador imediatamente após a instalação
- Mantenha o sistema atualizado regularmente
- Use HTTPS para todas as comunicações
- Limite o acesso ao painel apenas a IPs confiáveis, se possível
- Faça backup regular do banco de dados e das sessões do WhatsApp

## Limitações e Avisos

- O uso de APIs não oficiais do WhatsApp pode violar os Termos de Serviço
- O WhatsApp pode detectar e bloquear números usados com automação
- As bibliotecas podem parar de funcionar após atualizações do WhatsApp
- Recomenda-se usar números dedicados para automação, não números pessoais importantes

## Suporte

Para suporte técnico ou dúvidas sobre o sistema, entre em contato através do e-mail: suporte@seudominio.com
