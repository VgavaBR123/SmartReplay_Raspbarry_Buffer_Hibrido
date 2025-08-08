#!/bin/bash
# Script de instalação para Raspberry Pi OS / Ubuntu / Debian
# Sistema de Buffer de Vídeo RTSP

set -e

echo "================================================"
echo "Instalação - Sistema de Buffer de Vídeo RTSP"
echo "================================================"

# Verificar se está rodando como root
if [[ $EUID -eq 0 ]]; then
   echo "ERRO: Não execute este script como root"
   echo "Execute: bash scripts/install.sh"
   exit 1
fi

# Verificar sistema operacional
if [[ ! -f /etc/debian_version ]]; then
    echo "AVISO: Este script foi testado apenas em sistemas Debian/Ubuntu"
    echo "Continuando mesmo assim..."
fi

echo "1. Atualizando sistema..."
sudo apt update

echo "2. Instalando dependências do sistema..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    curl \
    jq \
    htop

echo "3. Verificando versão do FFmpeg..."
ffmpeg -version | head -n 1

echo "4. Verificando tmpfs..."
if mount | grep -q "/dev/shm"; then
    echo "✓ tmpfs já está montado em /dev/shm"
    df -h /dev/shm
else
    echo "⚠ tmpfs não encontrado. Configurando..."
    sudo mkdir -p /dev/shm
    sudo mount -t tmpfs -o size=2G tmpfs /dev/shm
    echo "tmpfs /dev/shm tmpfs defaults,size=2048M 0 0" | sudo tee -a /etc/fstab
fi

echo "5. Criando ambiente virtual Python..."
if [[ ! -d "venv" ]]; then
    python3 -m venv venv
fi

echo "6. Ativando ambiente virtual e instalando dependências..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "7. Verificando configuração..."
if [[ ! -f "config.env" ]]; then
    echo "⚠ Arquivo config.env não encontrado"
    echo "Configure as URLs das câmeras antes de executar"
else
    echo "✓ Arquivo de configuração encontrado"
fi

echo "8. Criando diretórios necessários..."
mkdir -p clips temp_videos logs

echo "9. Configurando permissões..."
chmod +x main.py
chmod +x scripts/*.sh

# Verificar se é Raspberry Pi
if [[ -f /proc/device-tree/model ]] && grep -q "Raspberry Pi" /proc/device-tree/model; then
    echo ""
    echo "==============================================="
    echo "CONFIGURAÇÕES ESPECÍFICAS PARA RASPBERRY PI"
    echo "==============================================="
    
    echo "10. Configurando split de memória GPU..."
    if ! grep -q "gpu_mem=64" /boot/config.txt; then
        echo "gpu_mem=64" | sudo tee -a /boot/config.txt
        echo "✓ Split de memória configurado (requer reinicialização)"
    fi
    
    echo "11. Otimizando configurações de rede..."
    if ! grep -q "net.core.rmem_max" /etc/sysctl.conf; then
        sudo tee -a /etc/sysctl.conf << EOF

# Otimizações para streaming de vídeo
net.core.rmem_max = 134217728
net.core.wmem_max = 134217728
net.ipv4.tcp_rmem = 4096 87380 134217728
net.ipv4.tcp_wmem = 4096 65536 134217728
EOF
        echo "✓ Configurações de rede otimizadas"
    fi
    
    echo "12. Configurando swappiness..."
    if ! grep -q "vm.swappiness" /etc/sysctl.conf; then
        echo "vm.swappiness=10" | sudo tee -a /etc/sysctl.conf
        echo "✓ Swappiness configurado para 10"
    fi
fi

echo ""
echo "================================================"
echo "INSTALAÇÃO CONCLUÍDA COM SUCESSO!"
echo "================================================"
echo ""
echo "Próximos passos:"
echo "1. Configure as URLs das câmeras em config.env"
echo "2. Execute: source venv/bin/activate"
echo "3. Execute: python3 main.py"
echo ""
echo "Para executar como serviço:"
echo "1. Execute: sudo bash scripts/setup-service.sh"
echo ""
echo "Para testar conectividade:"
echo "1. Execute: bash scripts/test-cameras.sh"
echo ""

# Verificar se precisa reiniciar (apenas para Raspberry Pi)
if [[ -f /proc/device-tree/model ]] && grep -q "Raspberry Pi" /proc/device-tree/model; then
    echo "⚠ RECOMENDADO: Reinicie o sistema para aplicar otimizações"
    echo "   Execute: sudo reboot"
fi
