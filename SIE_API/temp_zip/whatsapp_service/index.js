// Atualizar o arquivo index.js para incluir a integração com n8n
const express = require('express');
const http = require('http');
const socketIo = require('socket.io');
const cors = require('cors');
const { Client, LocalAuth } = require('whatsapp-web.js');
const { default: makeWASocket, DisconnectReason, useMultiFileAuthState } = require('@whiskeysockets/baileys');
const qrcode = require('qrcode-terminal');
const fs = require('fs');
const path = require('path');
const axios = require('axios');
const setupN8nIntegration = require('./n8n_integration');

// Configuração do servidor Express
const app = express();
const server = http.createServer(app);
const io = socketIo(server, {
  cors: {
    origin: '*',
    methods: ['GET', 'POST']
  }
});

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Diretório para armazenar dados das sessões
const SESSIONS_DIR = path.join(__dirname, 'sessions');
if (!fs.existsSync(SESSIONS_DIR)) {
  fs.mkdirSync(SESSIONS_DIR, { recursive: true });
}

// Armazenamento de instâncias ativas
const instances = {};
const baileysSessions = {};

// Função para criar diretório de sessão
const createSessionDir = (sessionId) => {
  const sessionDir = path.join(SESSIONS_DIR, sessionId);
  if (!fs.existsSync(sessionDir)) {
    fs.mkdirSync(sessionDir, { recursive: true });
  }
  return sessionDir;
};

// Função para inicializar cliente WhatsApp-Web.js
const initWhatsAppWebClient = async (sessionId, socketId) => {
  const sessionDir = createSessionDir(sessionId);
  
  const client = new Client({
    authStrategy: new LocalAuth({ clientId: sessionId, dataPath: sessionDir }),
    puppeteer: {
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-accelerated-2d-canvas', '--no-first-run', '--no-zygote', '--single-process', '--disable-gpu']
    }
  });

  // Evento de geração de QR code
  client.on('qr', (qr) => {
    console.log(`QR Code gerado para sessão ${sessionId}`);
    qrcode.generate(qr, { small: true });
    io.to(socketId).emit('qr', { sessionId, qr });
  });

  // Evento de autenticação
  client.on('authenticated', () => {
    console.log(`Sessão ${sessionId} autenticada`);
    io.to(socketId).emit('authenticated', { sessionId });
  });

  // Evento de pronto
  client.on('ready', () => {
    console.log(`Cliente ${sessionId} está pronto`);
    io.to(socketId).emit('ready', { sessionId });
  });

  // Evento de mensagem recebida
  client.on('message', async (message) => {
    console.log(`Mensagem recebida na sessão ${sessionId}`);
    
    // Verificar se é mensagem de grupo e se deve ser ignorada para o n8n
    const chat = await message.getChat();
    const isGroup = chat.isGroup;
    
    // Enviar para o socket
    io.to(socketId).emit('message', { 
      sessionId, 
      message: {
        from: message.from,
        body: message.body,
        hasMedia: message.hasMedia,
        isGroup,
        timestamp: message.timestamp,
        type: message.type
      }
    });
    
    // Enviar para webhook do n8n
    if (instances[sessionId]?.webhook) {
      const { sendEventToN8n } = n8nIntegration;
      sendEventToN8n(sessionId, 'message', {
        from: message.from,
        body: message.body,
        hasMedia: message.hasMedia,
        isGroup,
        timestamp: message.timestamp,
        type: message.type
      });
    }
  });

  // Evento de desconexão
  client.on('disconnected', (reason) => {
    console.log(`Cliente ${sessionId} desconectado:`, reason);
    io.to(socketId).emit('disconnected', { sessionId, reason });
    
    // Tentar reconectar automaticamente
    client.initialize().catch(err => {
      console.error(`Erro ao reinicializar cliente ${sessionId}:`, err);
    });
  });

  // Inicializar cliente
  try {
    await client.initialize();
    instances[sessionId] = { client, type: 'whatsapp-web.js', socketId };
    return client;
  } catch (error) {
    console.error(`Erro ao inicializar cliente ${sessionId}:`, error);
    throw error;
  }
};

// Função para inicializar cliente Baileys
const initBaileysClient = async (sessionId, socketId) => {
  const sessionDir = createSessionDir(sessionId);
  const { state, saveCreds } = await useMultiFileAuthState(path.join(sessionDir, 'baileys_auth_info'));
  
  const sock = makeWASocket({
    auth: state,
    printQRInTerminal: true
  });
  
  // Evento de conexão
  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;
    
    if (qr) {
      console.log(`QR Code Baileys gerado para sessão ${sessionId}`);
      io.to(socketId).emit('qr', { sessionId, qr });
    }
    
    if (connection === 'open') {
      console.log(`Conexão Baileys aberta para sessão ${sessionId}`);
      io.to(socketId).emit('ready', { sessionId });
    }
    
    if (connection === 'close') {
      const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
      console.log(`Conexão Baileys fechada para sessão ${sessionId}, reconectar: ${shouldReconnect}`);
      
      if (shouldReconnect) {
        initBaileysClient(sessionId, socketId);
      } else {
        io.to(socketId).emit('disconnected', { sessionId, reason: 'logged_out' });
      }
    }
  });
  
  // Evento de credenciais atualizadas
  sock.ev.on('creds.update', saveCreds);
  
  // Evento de mensagem recebida
  sock.ev.on('messages.upsert', async ({ messages }) => {
    for (const message of messages) {
      if (!message.key.fromMe) {
        console.log(`Mensagem Baileys recebida na sessão ${sessionId}`);
        
        const isGroup = message.key.remoteJid.endsWith('@g.us');
        const messageData = {
          from: message.key.remoteJid,
          body: message.message?.conversation || message.message?.extendedTextMessage?.text || '',
          hasMedia: !!message.message?.imageMessage || !!message.message?.audioMessage,
          isGroup,
          timestamp: message.messageTimestamp,
          type: 'baileys'
        };
        
        // Enviar para o socket
        io.to(socketId).emit('message', { 
          sessionId, 
          message: messageData
        });
        
        // Enviar para webhook do n8n
        if (baileysSessions[sessionId]?.webhook) {
          const { sendEventToN8n } = n8nIntegration;
          sendEventToN8n(sessionId, 'message', messageData);
        }
      }
    }
  });
  
  baileysSessions[sessionId] = { sock, socketId };
  return sock;
};

// Socket.io para comunicação em tempo real
io.on('connection', (socket) => {
  console.log(`Nova conexão socket: ${socket.id}`);
  
  // Iniciar nova instância
  socket.on('init', async ({ sessionId, type = 'whatsapp-web.js' }) => {
    try {
      console.log(`Inicializando sessão ${sessionId} com ${type}`);
      
      if (type === 'whatsapp-web.js') {
        await initWhatsAppWebClient(sessionId, socket.id);
      } else if (type === 'baileys') {
        await initBaileysClient(sessionId, socket.id);
      }
      
      socket.emit('init_response', { success: true, sessionId, type });
    } catch (error) {
      console.error(`Erro ao inicializar sessão ${sessionId}:`, error);
      socket.emit('init_response', { success: false, error: error.message });
    }
  });
  
  // Desconectar instância
  socket.on('logout', async ({ sessionId }) => {
    try {
      if (instances[sessionId]) {
        await instances[sessionId].client.logout();
        delete instances[sessionId];
      } else if (baileysSessions[sessionId]) {
        delete baileysSessions[sessionId];
      }
      
      socket.emit('logout_response', { success: true, sessionId });
    } catch (error) {
      console.error(`Erro ao desconectar sessão ${sessionId}:`, error);
      socket.emit('logout_response', { success: false, error: error.message });
    }
  });
  
  // Desconexão do socket
  socket.on('disconnect', () => {
    console.log(`Socket desconectado: ${socket.id}`);
    // Não desconectar instâncias WhatsApp para manter persistência
  });
});

// Configurar integração com n8n
const n8nIntegration = setupN8nIntegration(app, instances, baileysSessions);

// Rotas da API

// Listar todas as instâncias
app.get('/api/instances', (req, res) => {
  const activeInstances = Object.keys(instances).map(id => ({
    id,
    type: instances[id].type,
    status: instances[id].client.info ? 'connected' : 'connecting'
  }));
  
  const baileysList = Object.keys(baileysSessions).map(id => ({
    id,
    type: 'baileys',
    status: 'connected' // Simplificado, poderia verificar estado real
  }));
  
  res.json([...activeInstances, ...baileysList]);
});

// Enviar mensagem de texto
app.post('/api/send-message', async (req, res) => {
  try {
    const { sessionId, to, message, type = 'whatsapp-web.js' } = req.body;
    
    if (type === 'whatsapp-web.js') {
      if (!instances[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância não encontrada' });
      }
      
      const result = await instances[sessionId].client.sendMessage(to, message);
      res.json({ success: true, result });
    } else if (type === 'baileys') {
      if (!baileysSessions[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância Baileys não encontrada' });
      }
      
      await baileysSessions[sessionId].sock.sendMessage(to, { text: message });
      res.json({ success: true });
    }
  } catch (error) {
    console.error('Erro ao enviar mensagem:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Enviar mídia (imagem, áudio, etc.)
app.post('/api/send-media', async (req, res) => {
  try {
    const { sessionId, to, mediaUrl, caption, mediaType, type = 'whatsapp-web.js' } = req.body;
    
    if (type === 'whatsapp-web.js') {
      if (!instances[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância não encontrada' });
      }
      
      const client = instances[sessionId].client;
      let media;
      
      // Se for URL, baixar o arquivo
      if (mediaUrl.startsWith('http')) {
        const response = await axios.get(mediaUrl, { responseType: 'arraybuffer' });
        media = Buffer.from(response.data, 'binary');
      } else {
        // Se for caminho local
        media = mediaUrl;
      }
      
      let result;
      if (mediaType === 'image') {
        const messageMedia = new (require('whatsapp-web.js')).MessageMedia('image/jpeg', media.toString('base64'));
        result = await client.sendMessage(to, messageMedia, { caption });
      } else if (mediaType === 'audio') {
        const messageMedia = new (require('whatsapp-web.js')).MessageMedia('audio/mp3', media.toString('base64'));
        result = await client.sendMessage(to, messageMedia);
      } else if (mediaType === 'document') {
        const messageMedia = new (require('whatsapp-web.js')).MessageMedia('application/pdf', media.toString('base64'));
        result = await client.sendMessage(to, messageMedia, { caption });
      }
      
      res.json({ success: true, result });
    } else if (type === 'baileys') {
      if (!baileysSessions[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância Baileys não encontrada' });
      }
      
      const sock = baileysSessions[sessionId].sock;
      
      // Implementação para Baileys
      // Esta parte varia dependendo do tipo de mídia
      if (mediaType === 'image') {
        await sock.sendMessage(to, { 
          image: { url: mediaUrl }, 
          caption 
        });
      } else if (mediaType === 'audio') {
        await sock.sendMessage(to, { 
          audio: { url: mediaUrl }, 
          mimetype: 'audio/mp4'
        });
      } else if (mediaType === 'document') {
        await sock.sendMessage(to, { 
          document: { url: mediaUrl }, 
          mimetype: 'application/pdf',
          caption
        });
      }
      
      res.json({ success: true });
    }
  } catch (error) {
    console.error('Erro ao enviar mídia:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Marcar todos em um grupo
app.post('/api/mention-all', async (req, res) => {
  try {
    const { sessionId, groupId, message, anonymous = false, type = 'whatsapp-web.js' } = req.body;
    
    if (type === 'whatsapp-web.js') {
      if (!instances[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância não encontrada' });
      }
      
      const client = instances[sessionId].client;
      const chat = await client.getChatById(groupId);
      
      if (!chat.isGroup) {
        return res.status(400).json({ success: false, error: 'O ID fornecido não é de um grupo' });
      }
      
      const participants = chat.participants.map(p => p.id._serialized);
      
      // Se for anônimo, usar a palavra-chave "cita!"
      let finalMessage = message;
      if (anonymous && message.includes('cita!')) {
        finalMessage = message.replace('cita!', '');
        
        // Criar menções para todos os participantes
        let mentions = [];
        for (const participant of participants) {
          mentions.push(await client.getContactById(participant));
        }
        
        await chat.sendMessage(finalMessage, { mentions });
      } else {
        // Mencionar todos normalmente
        let mentionText = '';
        let mentions = [];
        
        for (const participant of participants) {
          const contact = await client.getContactById(participant);
          mentionText += `@${participant.split('@')[0]} `;
          mentions.push(contact);
        }
        
        await chat.sendMessage(`${mentionText}\n${message}`, { mentions });
      }
      
      res.json({ success: true });
    } else if (type === 'baileys') {
      if (!baileysSessions[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância Baileys não encontrada' });
      }
      
      const sock = baileysSessions[sessionId].sock;
      
      // Obter participantes do grupo
      const metadata = await sock.groupMetadata(groupId);
      const participants = metadata.participants.map(p => p.id);
      
      // Criar menções
      const mentions = participants.map(jid => ({ mentioned: jid }));
      
      // Se for anônimo, usar a palavra-chave "cita!"
      let finalMessage = message;
      if (anonymous && message.includes('cita!')) {
        finalMessage = message.replace('cita!', '');
      } else {
        // Adicionar @menção para cada participante
        let mentionText = '';
        for (const participant of participants) {
          mentionText += `@${participant.split('@')[0]} `;
        }
        finalMessage = `${mentionText}\n${message}`;
      }
      
      await sock.sendMessage(groupId, { 
        text: finalMessage,
        mentions: participants
      });
      
      res.json({ success: true });
    }
  } catch (error) {
    console.error('Erro ao mencionar todos:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Bloquear número
app.post('/api/block-contact', async (req, res) => {
  try {
    const { sessionId, contactId, type = 'whatsapp-web.js' } = req.body;
    
    if (type === 'whatsapp-web.js') {
      if (!instances[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância não encontrada' });
      }
      
      const client = instances[sessionId].client;
      await client.blockContact(contactId);
      res.json({ success: true });
    } else if (type === 'baileys') {
      if (!baileysSessions[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância Baileys não encontrada' });
      }
      
      const sock = baileysSessions[sessionId].sock;
      await sock.updateBlockStatus(contactId, "block");
      res.json({ success: true });
    }
  } catch (error) {
    console.error('Erro ao bloquear contato:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Desbloquear número
app.post('/api/unblock-contact', async (req, res) => {
  try {
    const { sessionId, contactId, type = 'whatsapp-web.js' } = req.body;
    
    if (type === 'whatsapp-web.js') {
      if (!instances[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância não encontrada' });
      }
      
      const client = instances[sessionId].client;
      await client.unblockContact(contactId);
      res.json({ success: true });
    } else if (type === 'baileys') {
      if (!baileysSessions[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância Baileys não encontrada' });
      }
      
      const sock = baileysSessions[sessionId].sock;
      await sock.updateBlockStatus(contactId, "unblock");
      res.json({ success: true });
    }
  } catch (error) {
    console.error('Erro ao desbloquear contato:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Obter todos os contatos
app.get('/api/contacts/:sessionId', async (req, res) => {
  try {
    const { sessionId } = req.params;
    const { type = 'whatsapp-web.js' } = req.query;
    
    if (type === 'whatsapp-web.js') {
      if (!instances[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância não encontrada' });
      }
      
      const client = instances[sessionId].client;
      const contacts = await client.getContacts();
      res.json({ success: true, contacts });
    } else if (type === 'baileys') {
      if (!baileysSessions[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância Baileys não encontrada' });
      }
      
      const sock = baileysSessions[sessionId].sock;
      // Implementação para Baileys
      // Esta parte depende da estrutura específica do Baileys
      res.json({ success: true, contacts: [] });
    }
  } catch (error) {
    console.error('Erro ao obter contatos:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Obter todas as conversas
app.get('/api/chats/:sessionId', async (req, res) => {
  try {
    const { sessionId } = req.params;
    const { type = 'whatsapp-web.js' } = req.query;
    
    if (type === 'whatsapp-web.js') {
      if (!instances[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância não encontrada' });
      }
      
      const client = instances[sessionId].client;
      const chats = await client.getChats();
      res.json({ success: true, chats });
    } else if (type === 'baileys') {
      if (!baileysSessions[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância Baileys não encontrada' });
      }
      
      // Implementação para Baileys
      // Esta parte depende da estrutura específica do Baileys
      res.json({ success: true, chats: [] });
    }
  } catch (error) {
    console.error('Erro ao obter conversas:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Configurar webhook para n8n
app.post('/api/set-webhook', (req, res) => {
  try {
    const { sessionId, url, ignoreGroups = false } = req.body;
    
    // Armazenar configuração de webhook
    if (instances[sessionId]) {
      instances[sessionId].webhook = { url, ignoreGroups };
    } else if (baileysSessions[sessionId]) {
      baileysSessions[sessionId].webhook = { url, ignoreGroups };
    } else {
      return res.status(404).json({ success: false, error: 'Instância não encontrada' });
    }
    
    res.json({ success: true });
  } catch (error) {
    console.error('Erro ao configurar webhook:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Enviar botões interativos (apenas whatsapp-web.js)
app.post('/api/send-buttons', async (req, res) => {
  try {
    const { sessionId, to, title, buttons } = req.body;
    
    if (!instances[sessionId]) {
      return res.status(404).json({ success: false, error: 'Instância não encontrada' });
    }
    
    const client = instances[sessionId].client;
    
    // Implementação de botões
    // Esta funcionalidade pode variar dependendo da versão da biblioteca
    // e das limitações da API do WhatsApp
    
    res.json({ success: true, message: 'Funcionalidade de botões em desenvolvimento' });
  } catch (error) {
    console.error('Erro ao enviar botões:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Verificar status
app.get('/api/status/:sessionId', async (req, res) => {
  try {
    const { sessionId } = req.params;
    const { type = 'whatsapp-web.js' } = req.query;
    
    if (type === 'whatsapp-web.js') {
      if (!instances[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância não encontrada' });
      }
      
      const client = instances[sessionId].client;
      const status = {
        connected: client.info ? true : false,
        info: client.info
      };
      
      res.json({ success: true, status });
    } else if (type === 'baileys') {
      if (!baileysSessions[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância Baileys não encontrada' });
      }
      
      // Implementação para Baileys
      res.json({ success: true, status: { connected: true } });
    }
  } catch (error) {
    console.error('Erro ao verificar status:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Iniciar servidor
const PORT = process.env.PORT || 3000;
server.listen(PORT, '0.0.0.0', () => {
  console.log(`Servidor SIE API rodando na porta ${PORT}`);
});
