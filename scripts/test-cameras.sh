#!/bin/bash
# Script para testar conectividade das câmeras RTSP
# Sistema de Buffer de Vídeo RTSP

set -e

echo "==============================================="
echo "Teste de Conectividade das Câmeras RTSP"
echo "==============================================="

# Verificar se config.env existe
if [[ ! -f "config.env" ]]; then
    echo "ERRO: Arquivo config.env não encontrado"
    echo "Crie o arquivo com as configurações das câmeras"
    exit 1
fi

# Carregar configurações
source config.env

echo "Carregando configurações do arquivo config.env..."
echo ""

# Função para testar uma câmera
test_camera() {
    local camera_name="$1"
    local camera_url="$2"
    
    if [[ -z "$camera_url" ]]; then
        return
    fi
    
    echo "Testando $camera_name..."
    echo "URL: $camera_url"
    echo "----------------------------------------"
    
    # Extrair informações da URL para teste de ping
    local ip=$(echo "$camera_url" | sed -n 's|.*://.*@\([^:]*\):.*|\1|p')
    if [[ -z "$ip" ]]; then
        ip=$(echo "$camera_url" | sed -n 's|.*://\([^:]*\):.*|\1|p')
    fi
    
    # Teste de ping
    if [[ -n "$ip" ]]; then
        echo -n "Ping para $ip: "
        if ping -c 3 -W 2 "$ip" >/dev/null 2>&1; then
            echo "✓ OK"
        else
            echo "✗ FALHA"
            echo "  Câmera não responde ao ping"
            echo ""
            return 1
        fi
    fi
    
    # Teste de conectividade RTSP com timeout
    echo -n "Teste RTSP: "
    local transport="${RTSP_TRANSPORT:-tcp}"
    
    timeout 15 ffmpeg \
        -loglevel error \
        -rtsp_transport "$transport" \
        -i "$camera_url" \
        -t 3 \
        -f null \
        - >/dev/null 2>&1
    
    local exit_code=$?
    
    if [[ $exit_code -eq 0 ]]; then
        echo "✓ OK"
        
        # Obter informações do stream
        echo "Informações do stream:"
        timeout 10 ffprobe \
            -loglevel quiet \
            -rtsp_transport "$transport" \
            -show_streams \
            -select_streams v:0 \
            -of csv=p=0:s=x \
            -show_entries stream=codec_name,width,height,r_frame_rate \
            "$camera_url" 2>/dev/null | \
        while IFS='x' read -r codec width height framerate; do
            echo "  Codec: $codec"
            echo "  Resolução: ${width}x${height}"
            echo "  Frame rate: $framerate"
        done
        
    elif [[ $exit_code -eq 124 ]]; then
        echo "✗ TIMEOUT"
        echo "  Conexão demorou mais de 15 segundos"
    else
        echo "✗ FALHA"
        echo "  Verifique URL, credenciais e codec"
        
        # Teste detalhado para debug
        echo "  Executando teste detalhado..."
        timeout 10 ffmpeg \
            -loglevel warning \
            -rtsp_transport "$transport" \
            -i "$camera_url" \
            -t 1 \
            -f null \
            - 2>&1 | head -n 5 | sed 's/^/    /'
    fi
    
    echo ""
    return $exit_code
}

# Contador de sucessos/falhas
success_count=0
total_count=0

# Testar cada câmera configurada
for i in {1..10}; do
    camera_var="CAMERA_${i}_URL"
    camera_url="${!camera_var}"
    
    if [[ -n "$camera_url" ]]; then
        total_count=$((total_count + 1))
        if test_camera "Camera $i" "$camera_url"; then
            success_count=$((success_count + 1))
        fi
    fi
done

# Resumo final
echo "==============================================="
echo "RESUMO DOS TESTES"
echo "==============================================="
echo "Câmeras testadas: $total_count"
echo "Sucessos: $success_count"
echo "Falhas: $((total_count - success_count))"
echo ""

if [[ $success_count -eq $total_count ]] && [[ $total_count -gt 0 ]]; then
    echo "🎉 TODAS AS CÂMERAS FUNCIONANDO!"
    echo ""
    echo "Próximos passos:"
    echo "1. Execute o sistema: python3 main.py"
    echo "2. Ou instale como serviço: sudo bash scripts/setup-service.sh"
    
elif [[ $success_count -gt 0 ]]; then
    echo "⚠ ALGUMAS CÂMERAS COM PROBLEMAS"
    echo ""
    echo "Verificações para câmeras com falha:"
    echo "- URL e porta corretas"
    echo "- Credenciais válidas"
    echo "- Câmera ligada e acessível na rede"
    echo "- Codec suportado (H.264 recomendado)"
    echo "- Firewall não bloqueando acesso"
    
else
    echo "❌ NENHUMA CÂMERA FUNCIONANDO"
    echo ""
    echo "Verificações gerais:"
    echo "- Arquivo config.env configurado corretamente"
    echo "- Rede funcionando (teste: ping 8.8.8.8)"
    echo "- FFmpeg instalado (teste: ffmpeg -version)"
    echo "- URLs no formato: rtsp://usuario:senha@ip:porta/caminho"
    
fi

echo ""
echo "Para mais informações, consulte README.txt"
