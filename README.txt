SISTEMA DE BUFFER DE VÍDEO RTSP - RASPBERRY PI
===============================================

Este sistema implementa um buffer de vídeo robusto para captura de múltiplas 
câmeras IP via RTSP, com segmentação automática, armazenamento em buffer na 
RAM (tmpfs) e geração de clipes de duração exata sob demanda.

CARACTERÍSTICAS PRINCIPAIS
==========================

✓ Captura simultânea de múltiplas câmeras RTSP
✓ Buffer circular em RAM/tmpfs para evitar desgaste do SD/SSD
✓ Segmentação automática com alinhamento de timestamp
✓ Geração de clipes com duração exata (25s por padrão)
✓ Gatilho via teclado ou HTTP endpoint
✓ Reconexão automática com backoff exponencial
✓ Sistema de monitoramento e resiliência
✓ Logs estruturados em JSON
✓ Compatível com Raspberry Pi, Windows e Linux

ARQUITETURA DO SISTEMA
=====================

┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Câmeras IP    │───▶│   FFmpeg RTSP    │───▶│  Buffer Circular│
│   (RTSP)        │    │   Segmentação    │    │   (RAM/tmpfs)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                        │
┌─────────────────┐    ┌──────────────────┐            │
│ Gatilho Manual  │───▶│  Gerador Clipes  │◄───────────┘
│ (Teclado/HTTP)  │    │  (Concatenação)  │
└─────────────────┘    └──────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Clipes Salvos   │
                       │ (Disco Físico)  │
                       └─────────────────┘

REQUISITOS DO SISTEMA
====================

Hardware Mínimo:
- Raspberry Pi 4B (8GB RAM recomendado, 4GB mínimo)
- Cartão SD Classe 10 (32GB+) ou SSD USB 3.0
- Conectividade de rede estável

Software:
- Raspberry Pi OS (Bullseye ou posterior)
- Python 3.8+
- FFmpeg 4.0+
- 2-4GB RAM disponível para buffer

Câmeras:
- Suporte RTSP (H.264 recomendado)
- Resolução máxima: 1920x1080 @ 30fps
- Bitrate recomendado: 2-6 Mbps por câmera

INSTALAÇÃO
==========

1. Preparação do Sistema
   ----------------------
   # Atualizar sistema
   sudo apt update && sudo apt upgrade -y
   
   # Instalar dependências
   sudo apt install python3 python3-pip ffmpeg git -y
   
   # Verificar tmpfs (deve mostrar /dev/shm)
   df -h | grep tmpfs

2. Download e Configuração
   -----------------------
   # Clonar ou extrair o projeto
   cd /home/pi
   git clone <repositorio> video-buffer-system
   cd video-buffer-system
   
   # Instalar dependências Python
   pip3 install -r requirements.txt

3. Configuração das Câmeras
   ------------------------
   # Editar arquivo de configuração
   nano config.env
   
   # Configurar URLs das câmeras:
   CAMERA_1_URL=rtsp://admin:123456@192.168.226.201:554/profile1
   CAMERA_2_URL=rtsp://admin:123456@192.168.226.202:554/profile1
   
   # Ajustar parâmetros conforme necessário

4. Teste de Conectividade
   ----------------------
   # Testar conectividade RTSP
   ffmpeg -rtsp_transport tcp -i "rtsp://admin:123456@192.168.1.100:554/profile1" -t 10 -f null -
   
   # Deve mostrar informações do stream sem erros

CONFIGURAÇÃO DETALHADA
=====================

Arquivo config.env - Parâmetros Principais:
-------------------------------------------

# URLs das Câmeras
CAMERA_1_URL=rtsp://admin:senha@192.168.1.100:554/profile1
CAMERA_2_URL=rtsp://admin:senha@192.168.1.101:554/profile1

# Parâmetros de Segmentação
CHUNK_DURATION=5              # Duração de cada segmento (segundos)
BUFFER_SECONDS=30             # Total mantido no buffer (segundos)
FINAL_CLIP_DURATION=25        # Duração do clipe final (segundos)

# Diretórios
TEMP_DIR=/dev/shm             # Buffer em RAM (Linux tmpfs)
CLIPS_DIR=./clips             # Clipes salvos permanentemente

# Modo de Gatilho
TRIGGER_MODE=keyboard         # keyboard ou http
HTTP_PORT=8080                # Porta para modo HTTP

# Configurações de Reconexão
RECONNECT_INITIAL_DELAY=2     # Delay inicial (segundos)
RECONNECT_MAX_DELAY=30        # Delay máximo (segundos)
RECONNECT_MAX_ATTEMPTS=0      # 0 = infinito

# Configurações FFmpeg
FFMPEG_KEYFRAME_INTERVAL=1    # Keyframe a cada N segundos
FFMPEG_PRESET=ultrafast       # Preset de codificação
FFMPEG_CRF=23                 # Qualidade (15-30, menor = melhor)

EXECUÇÃO DO SISTEMA
==================

1. Execução Básica
   ---------------
   # Executar sistema
   python3 main.py
   
   # O sistema irá:
   # - Carregar configurações
   # - Inicializar todos os componentes
   # - Começar captura de todas as câmeras
   # - Aguardar comandos de gatilho

2. Controles Durante Execução
   --------------------------
   Modo Keyboard:
   - Pressionar 's' + ENTER: Salvar clipe de todas as câmeras
   - Pressionar 'q' + ENTER: Sair do sistema
   
   Modo HTTP:
   - POST http://localhost:8080/save-clip: Salvar clipe
   - GET http://localhost:8080/status: Ver status do sistema
   - GET http://localhost:8080/health: Health check

3. Exemplo de Uso HTTP
   -------------------
   # Salvar clipe de todas as câmeras
   curl -X POST http://localhost:8080/save-clip
   
   # Salvar clipe de câmera específica
   curl -X POST http://localhost:8080/save-clip \
        -H "Content-Type: application/json" \
        -d '{"camera_id": "camera_1", "duration": 20}'
   
   # Verificar status
   curl http://localhost:8080/status

FUNCIONAMENTO INTERNO
====================

1. Fluxo de Captura
   ----------------
   a) FFmpeg conecta via RTSP às câmeras
   b) Stream é segmentado em chunks de 5s alinhados ao relógio
   c) Keyframes a cada 1s para cortes precisos
   d) Chunks são salvos no tmpfs (/dev/shm)
   e) Buffer circular mantém apenas últimos 30s

2. Geração de Clipes
   -----------------
   a) Gatilho é acionado (teclado ou HTTP)
   b) Sistema identifica chunks necessários para 25s de vídeo
   c) Modo rápido: Se alinhado, concatena chunks sem reencode
   d) Modo preciso: Se não alinhado, concatena e corta com reencode
   e) Clipe final é salvo no diretório de clips

3. Sistema de Resiliência
   ----------------------
   a) Monitora saúde de cada componente a cada 10-30s
   b) Verifica: processo FFmpeg, idade dos chunks, uso de recursos
   c) Reconexão automática com backoff exponencial
   d) Limpeza de emergência em caso de falta de memória

ESTRUTURA DE ARQUIVOS
====================

video-buffer-system/
├── main.py                 # Script de entrada
├── config.env              # Configurações do sistema
├── requirements.txt        # Dependências Python
├── README.txt              # Esta documentação
├── src/                    # Código-fonte
│   ├── main.py             # Sistema principal
│   ├── config.py           # Gerenciador de configurações
│   ├── logger.py           # Sistema de logging
│   ├── buffer_manager.py   # Gerenciador de buffer circular
│   ├── rtsp_capture.py     # Captura RTSP com FFmpeg
│   ├── trigger_system.py   # Sistema de gatilhos
│   ├── clip_generator.py   # Gerador de clipes
│   └── resilience_manager.py # Sistema de resiliência
├── clips/                  # Clipes salvos (criado automaticamente)
├── temp_videos/            # Buffer temporário (criado automaticamente)
└── logs/                   # Logs do sistema (criado automaticamente)

MONITORAMENTO E LOGS
===================

1. Logs do Sistema
   ---------------
   Os logs são salvos em formato JSON em logs/system.log
   
   Tipos de eventos:
   - system_*: Eventos do sistema (startup, shutdown)
   - camera_*: Eventos de câmeras (captura, reconexão)
   - buffer_*: Eventos de buffer (criação/remoção de chunks)
   - clip_*: Eventos de geração de clipes
   - error_*: Erros e exceções

2. Monitoramento de Recursos
   -------------------------
   O sistema monitora automaticamente:
   - Uso de CPU e memória
   - Espaço em disco
   - Temperatura (Raspberry Pi)
   - Status das capturas RTSP
   - Idade dos últimos chunks capturados

3. Verificação Manual
   ------------------
   # Ver logs em tempo real
   tail -f logs/system.log | jq '.'
   
   # Verificar processos FFmpeg
   ps aux | grep ffmpeg
   
   # Verificar uso do tmpfs
   df -h /dev/shm
   
   # Listar chunks ativos
   ls -la /dev/shm/video_buffer/

SOLUÇÃO DE PROBLEMAS
===================

1. Câmera Não Conecta
   ------------------
   Sintoma: "Erro na captura RTSP" nos logs
   
   Verificações:
   a) Testar URL RTSP manualmente:
      ffmpeg -rtsp_transport tcp -i "RTSP_URL" -t 5 -f null -
   
   b) Verificar conectividade de rede:
      ping IP_DA_CAMERA
   
   c) Verificar credenciais e porta no config.env
   
   d) Tentar diferentes transportes (tcp/udp)

2. Buffer Cheio / Sistema Lento
   ----------------------------
   Sintoma: "Buffer crítico" nos logs, sistema lento
   
   Soluções:
   a) Verificar espaço tmpfs:
      df -h /dev/shm
   
   b) Reduzir BUFFER_SECONDS no config.env
   
   c) Reduzir qualidade/resolução das câmeras
   
   d) Verificar se há outros processos consumindo tmpfs

3. Clipes Não São Gerados
   ----------------------
   Sintoma: Gatilho acionado mas nenhum arquivo em clips/
   
   Verificações:
   a) Verificar se há chunks no buffer:
      ls -la /dev/shm/video_buffer/camera_*/
   
   b) Verificar logs de geração de clipes
   
   c) Verificar espaço em disco para clipes:
      df -h ./clips
   
   d) Verificar permissões de escrita

4. FFmpeg Falha Constantemente
   ---------------------------
   Sintoma: Reconexões frequentes, "FFmpeg terminou com código != 0"
   
   Verificações:
   a) Verificar se FFmpeg está instalado:
      ffmpeg -version
   
   b) Testar parâmetros FFmpeg manualmente
   
   c) Verificar logs detalhados do FFmpeg
   
   d) Reduzir FFMPEG_CRF ou mudar FFMPEG_PRESET

OTIMIZAÇÕES PARA RASPBERRY PI
=============================

1. Configuração de Memória
   ------------------------
   # Aumentar split de memória GPU/CPU
   sudo raspi-config
   # Advanced Options > Memory Split > 64 (mínimo)
   
   # Configurar tmpfs dedicado para buffer
   sudo nano /etc/fstab
   # Adicionar linha:
   tmpfs /dev/shm tmpfs defaults,size=2048M 0 0

2. Configuração de Rede
   --------------------
   # Aumentar buffers de rede
   sudo nano /etc/sysctl.conf
   # Adicionar:
   net.core.rmem_max = 134217728
   net.core.wmem_max = 134217728
   net.ipv4.tcp_rmem = 4096 87380 134217728
   net.ipv4.tcp_wmem = 4096 65536 134217728

3. Configuração de Storage
   -----------------------
   # Para longevidade do SD card, usar SSD externo para clips
   # Montar SSD USB em /mnt/storage
   # Alterar CLIPS_DIR=/mnt/storage/clips no config.env

4. Configurações de Desempenho
   ---------------------------
   # Desabilitar swap se usando tmpfs grande
   sudo dphys-swapfile swapoff
   sudo systemctl disable dphys-swapfile
   
   # Configurar governor CPU para performance
   echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

CONFIGURAÇÃO COMO SERVIÇO SYSTEMD
=================================

Para executar o sistema automaticamente na inicialização:

1. Criar arquivo de serviço:
   sudo nano /etc/systemd/system/video-buffer.service

[Unit]
Description=Sistema de Buffer de Vídeo RTSP
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/video-buffer-system
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=10
Environment=PYTHONPATH=/home/pi/video-buffer-system/src

[Install]
WantedBy=multi-user.target

2. Habilitar e iniciar serviço:
   sudo systemctl enable video-buffer.service
   sudo systemctl start video-buffer.service
   sudo systemctl status video-buffer.service

API HTTP REFERENCE
==================

Quando TRIGGER_MODE=http, o sistema expõe uma API REST:

POST /save-clip
---------------
Salva um clipe de vídeo

Parâmetros opcionais (JSON):
{
  "camera_id": "camera_1",  // "all" para todas (padrão)
  "duration": 25            // Duração em segundos (padrão config)
}

Resposta:
{
  "success": true,
  "message": "Clipe salvo com sucesso",
  "trigger_time": "2024-01-15T10:30:00.000Z",
  "camera_id": "camera_1"
}

GET /status
-----------
Retorna status completo do sistema

Resposta:
{
  "status": "running",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "captures": { ... },
  "buffers": { ... },
  "health": { ... }
}

GET /health
-----------
Health check simples

Resposta:
{
  "status": "healthy"
}

LIMITAÇÕES E CONSIDERAÇÕES
=========================

1. Limitações de Hardware
   ----------------------
   - Raspberry Pi 4: Máximo 4-6 câmeras 1080p simultâneas
   - RAM limitada: Buffer de ~30s para 2 câmeras ocupa ~500MB
   - CPU limitada: Codificação H.264 consome ~15% por câmera

2. Limitações de Rede
   ------------------
   - Ethernet preferível sobre WiFi para estabilidade
   - Largura de banda: ~6 Mbps por câmera 1080p
   - Latência: Evitar redes com alta latência/jitter

3. Limitações de Armazenamento
   ---------------------------
   - tmpfs limitado pela RAM disponível
   - SD cards: Vida útil limitada com gravação intensiva
   - Clipes: Podem consumir muito espaço (1GB/hora aproximadamente)

SUPORTE E CONTRIBUIÇÃO
=====================

Para suporte técnico:
- Verificar logs em logs/system.log
- Usar ferramentas de debug incluídas
- Documentar problema com logs relevantes

Para contribuições:
- Seguir estrutura modular existente
- Adicionar logs adequados para debugging
- Testar em ambiente Raspberry Pi real
- Manter compatibilidade com configurações existentes

CHANGELOG
=========

v1.0.0 - Release Inicial
- Implementação completa do sistema de buffer
- Suporte para múltiplas câmeras RTSP
- Buffer circular em RAM/tmpfs
- Geração de clipes com duração exata
- Sistema de resiliência e reconexão automática
- APIs de controle via teclado e HTTP
- Compatibilidade Raspberry Pi, Windows, Linux

LICENÇA
=======

Este software é fornecido "como está", sem garantias de qualquer tipo.
Uso por conta e risco próprio.

FIM DA DOCUMENTAÇÃO
==================
