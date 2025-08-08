#!/bin/bash
# Script para configurar o sistema como serviço systemd
# Sistema de Buffer de Vídeo RTSP

set -e

echo "==============================================="
echo "Configuração como Serviço Systemd"
echo "==============================================="

# Verificar se está rodando como root
if [[ $EUID -ne 0 ]]; then
   echo "ERRO: Execute este script como root"
   echo "Execute: sudo bash scripts/setup-service.sh"
   exit 1
fi

# Obter diretório atual e usuário
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
USER_NAME="${SUDO_USER:-$(logname 2>/dev/null || echo 'pi')}"

echo "Diretório do projeto: $PROJECT_DIR"
echo "Usuário: $USER_NAME"
echo ""

# Verificar se o projeto está configurado
if [[ ! -f "$PROJECT_DIR/config.env" ]]; then
    echo "ERRO: Arquivo config.env não encontrado"
    echo "Configure o sistema antes de instalar como serviço"
    exit 1
fi

if [[ ! -f "$PROJECT_DIR/main.py" ]]; then
    echo "ERRO: Script principal não encontrado"
    echo "Verifique se o projeto está completo"
    exit 1
fi

# Verificar se ambiente virtual existe
if [[ ! -d "$PROJECT_DIR/venv" ]]; then
    echo "AVISO: Ambiente virtual não encontrado"
    echo "Execute primeiro: bash scripts/install.sh"
    echo "Continuando mesmo assim..."
fi

echo "1. Criando arquivo de serviço systemd..."

# Criar arquivo de serviço
cat > /etc/systemd/system/video-buffer.service << EOF
[Unit]
Description=Sistema de Buffer de Vídeo RTSP
Documentation=file://$PROJECT_DIR/README.txt
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/main.py
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=video-buffer

# Variáveis de ambiente
Environment=PYTHONPATH=$PROJECT_DIR/src
Environment=PYTHONUNBUFFERED=1

# Limites de recursos
LimitNOFILE=65536
LimitMEMLOCK=infinity

# Configurações de segurança
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=false
ReadWritePaths=$PROJECT_DIR
ReadWritePaths=/dev/shm
ReadWritePaths=/tmp

[Install]
WantedBy=multi-user.target
EOF

echo "✓ Arquivo de serviço criado"

echo "2. Configurando permissões..."
chown root:root /etc/systemd/system/video-buffer.service
chmod 644 /etc/systemd/system/video-buffer.service

echo "3. Recarregando systemd..."
systemctl daemon-reload

echo "4. Habilitando serviço para inicialização automática..."
systemctl enable video-buffer.service

echo "5. Criando script de controle..."
cat > /usr/local/bin/video-buffer << 'EOF'
#!/bin/bash
# Script de controle para o Sistema de Buffer de Vídeo RTSP

case "$1" in
    start)
        sudo systemctl start video-buffer.service
        echo "Serviço iniciado"
        ;;
    stop)
        sudo systemctl stop video-buffer.service
        echo "Serviço parado"
        ;;
    restart)
        sudo systemctl restart video-buffer.service
        echo "Serviço reiniciado"
        ;;
    status)
        sudo systemctl status video-buffer.service
        ;;
    logs)
        if [[ "$2" == "-f" ]]; then
            sudo journalctl -u video-buffer.service -f
        else
            sudo journalctl -u video-buffer.service -n 50
        fi
        ;;
    enable)
        sudo systemctl enable video-buffer.service
        echo "Serviço habilitado para inicialização automática"
        ;;
    disable)
        sudo systemctl disable video-buffer.service
        echo "Serviço desabilitado da inicialização automática"
        ;;
    save-clip)
        if command -v curl >/dev/null 2>&1; then
            curl -X POST http://localhost:8080/save-clip 2>/dev/null || echo "Erro: Sistema não está rodando ou modo HTTP não habilitado"
        else
            echo "Erro: curl não está instalado"
        fi
        ;;
    system-status)
        if command -v curl >/dev/null 2>&1; then
            curl -s http://localhost:8080/status 2>/dev/null | jq . || echo "Erro: Sistema não está rodando ou modo HTTP não habilitado"
        else
            echo "Erro: curl ou jq não está instalado"
        fi
        ;;
    *)
        echo "Uso: $0 {start|stop|restart|status|logs|enable|disable|save-clip|system-status}"
        echo ""
        echo "Comandos:"
        echo "  start         - Iniciar serviço"
        echo "  stop          - Parar serviço"
        echo "  restart       - Reiniciar serviço"
        echo "  status        - Status do serviço"
        echo "  logs          - Ver logs (use -f para seguir)"
        echo "  enable        - Habilitar inicialização automática"
        echo "  disable       - Desabilitar inicialização automática"
        echo "  save-clip     - Salvar clipe via API"
        echo "  system-status - Status detalhado do sistema"
        echo ""
        echo "Exemplos:"
        echo "  $0 logs -f    - Seguir logs em tempo real"
        echo "  $0 save-clip  - Salvar clipe manualmente"
        exit 1
        ;;
esac
EOF

chmod +x /usr/local/bin/video-buffer
echo "✓ Script de controle criado em /usr/local/bin/video-buffer"

echo "6. Verificando configuração..."
systemctl status video-buffer.service --no-pager || true

echo ""
echo "==============================================="
echo "SERVIÇO CONFIGURADO COM SUCESSO!"
echo "==============================================="
echo ""
echo "Comandos disponíveis:"
echo "  video-buffer start    - Iniciar serviço"
echo "  video-buffer stop     - Parar serviço"
echo "  video-buffer status   - Ver status"
echo "  video-buffer logs     - Ver logs"
echo "  video-buffer logs -f  - Seguir logs"
echo ""
echo "Para iniciar o serviço agora:"
echo "  sudo systemctl start video-buffer.service"
echo ""
echo "Para ver logs em tempo real:"
echo "  video-buffer logs -f"
echo ""
echo "O serviço iniciará automaticamente na próxima reinicialização."
echo ""

# Perguntar se deseja iniciar agora
read -p "Deseja iniciar o serviço agora? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Iniciando serviço..."
    systemctl start video-buffer.service
    sleep 3
    
    echo ""
    echo "Status do serviço:"
    systemctl status video-buffer.service --no-pager
    
    echo ""
    echo "Para monitorar logs:"
    echo "  video-buffer logs -f"
fi
