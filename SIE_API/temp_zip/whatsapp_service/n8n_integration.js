/**
 * Integração com n8n para SIE API
 * Este arquivo contém as funções para integração com n8n e webhooks
 */

const express = require('express');
const router = express.Router();
const axios = require('axios');

// Configuração para integração com n8n
const setupN8nIntegration = (app, instances, baileysSessions) => {
  // Endpoint para receber webhooks do n8n
  app.post('/api/n8n/webhook/:sessionId', async (req, res) => {
    try {
      const { sessionId } = req.params;
      const { message, to, mediaUrl, mediaType, caption, groupId, mentionAll, anonymous } = req.body;
      
      // Verificar se a instância existe
      if (!instances[sessionId] && !baileysSessions[sessionId]) {
        return res.status(404).json({ success: false, error: 'Instância não encontrada' });
      }
      
      // Determinar o tipo de instância
      const instanceType = instances[sessionId] ? 'whatsapp-web.js' : 'baileys';
      
      // Processar a ação com base nos parâmetros recebidos
      if (message && to) {
        // Enviar mensagem de texto
        if (instanceType === 'whatsapp-web.js') {
          const result = await instances[sessionId].client.sendMessage(to, message);
          res.json({ success: true, result });
        } else {
          await baileysSessions[sessionId].sock.sendMessage(to, { text: message });
          res.json({ success: true });
        }
      } else if (mediaUrl && to && mediaType) {
        // Enviar mídia
        if (instanceType === 'whatsapp-web.js') {
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
        } else {
          const sock = baileysSessions[sessionId].sock;
          
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
      } else if (groupId && message && mentionAll) {
        // Mencionar todos em um grupo
        if (instanceType === 'whatsapp-web.js') {
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
        } else {
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
      } else {
        res.status(400).json({ success: false, error: 'Parâmetros insuficientes para executar uma ação' });
      }
    } catch (error) {
      console.error('Erro no webhook do n8n:', error);
      res.status(500).json({ success: false, error: error.message });
    }
  });

  // Endpoint para testar conexão com n8n
  app.get('/api/n8n/test', (req, res) => {
    res.json({ 
      success: true, 
      message: 'Conexão com n8n estabelecida com sucesso!',
      timestamp: new Date().toISOString()
    });
  });

  // Endpoint para listar todas as instâncias disponíveis para n8n
  app.get('/api/n8n/instances', (req, res) => {
    const activeInstances = Object.keys(instances).map(id => ({
      id,
      type: instances[id].type,
      status: instances[id].client.info ? 'connected' : 'connecting'
    }));
    
    const baileysList = Object.keys(baileysSessions).map(id => ({
      id,
      type: 'baileys',
      status: 'connected'
    }));
    
    res.json({ success: true, instances: [...activeInstances, ...baileysList] });
  });

  // Função para enviar eventos para o n8n via webhook
  const sendEventToN8n = async (sessionId, event, data) => {
    try {
      // Verificar se há webhook configurado para esta instância
      const webhookUrl = instances[sessionId]?.webhook?.url || baileysSessions[sessionId]?.webhook?.url;
      
      if (!webhookUrl) {
        return;
      }
      
      // Verificar se deve ignorar grupos
      const ignoreGroups = instances[sessionId]?.webhook?.ignoreGroups || baileysSessions[sessionId]?.webhook?.ignoreGroups;
      
      // Se for mensagem de grupo e estiver configurado para ignorar, não envia
      if (event === 'message' && data.isGroup && ignoreGroups) {
        return;
      }
      
      // Enviar evento para o webhook
      await axios.post(webhookUrl, {
        event,
        sessionId,
        data,
        timestamp: new Date().toISOString()
      });
      
      console.log(`Evento ${event} enviado para webhook de ${sessionId}`);
    } catch (error) {
      console.error(`Erro ao enviar evento para webhook de ${sessionId}:`, error);
    }
  };

  return {
    sendEventToN8n
  };
};

module.exports = setupN8nIntegration;
