#!/usr/bin/env python3
"""
Script de entrada para o Sistema de Buffer de Vídeo RTSP.
Este script pode ser executado diretamente para iniciar o sistema.
"""

import sys
import os
from pathlib import Path

# Adicionar diretório src ao path para imports
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
sys.path.insert(0, str(src_dir))

# Importar módulo principal
from main import main

if __name__ == "__main__":
    # Verificar se estamos no diretório correto
    if not (current_dir / "config.env").exists():
        print("ERRO: Execute o script a partir do diretório raiz do projeto")
        print("Exemplo: python main.py")
        sys.exit(1)
    
    # Executar sistema
    main()
