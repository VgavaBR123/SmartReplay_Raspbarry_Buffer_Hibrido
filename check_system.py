#!/usr/bin/env python3
"""
Script de verificação do sistema para validar instalação e configuração.
Executa testes básicos de todas as dependências e configurações.
"""

import sys
import os
import subprocess
import importlib
from pathlib import Path

def check_python_version():
    """Verifica versão do Python"""
    print("🐍 Verificando Python...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        print(f"   ✓ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"   ✗ Python {version.major}.{version.minor}.{version.micro} (requerido >= 3.8)")
        return False

def check_dependencies():
    """Verifica dependências Python"""
    print("\n📦 Verificando dependências Python...")
    
    required_packages = [
        ("python-dotenv", "dotenv"),
        ("psutil", "psutil"),
        ("flask", "flask")
    ]
    
    optional_packages = [
        "werkzeug"
    ]
    
    success = True
    
    for package_name, module_name in required_packages:
        try:
            importlib.import_module(module_name)
            print(f"   ✓ {package_name}")
        except ImportError:
            print(f"   ✗ {package_name} (requerido)")
            success = False
    
    for package in optional_packages:
        try:
            module_name = package.replace("-", "_")
            importlib.import_module(module_name)
            print(f"   ✓ {package} (opcional)")
        except ImportError:
            print(f"   ⚠ {package} (opcional)")
    
    return success

def check_ffmpeg():
    """Verifica instalação do FFmpeg"""
    print("\n🎬 Verificando FFmpeg...")
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"   ✓ {version_line}")
            return True
        else:
            print("   ✗ FFmpeg não funcionando corretamente")
            return False
    except FileNotFoundError:
        print("   ✗ FFmpeg não encontrado")
        print("     Instale com: sudo apt install ffmpeg (Linux)")
        print("     Ou baixe de: https://ffmpeg.org/download.html")
        return False
    except subprocess.TimeoutExpired:
        print("   ✗ FFmpeg não responde (timeout)")
        return False

def check_project_structure():
    """Verifica estrutura do projeto"""
    print("\n📁 Verificando estrutura do projeto...")
    
    required_files = [
        "config.env",
        "main.py",
        "requirements.txt",
        "src/main.py",
        "src/config.py",
        "src/logger.py",
        "src/buffer_manager.py",
        "src/rtsp_capture.py",
        "src/trigger_system.py",
        "src/clip_generator.py",
        "src/resilience_manager.py"
    ]
    
    optional_files = [
        "README.txt",
        "scripts/install.sh",
        "scripts/test-cameras.sh",
        "scripts/setup-service.sh"
    ]
    
    success = True
    
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"   ✓ {file_path}")
        else:
            print(f"   ✗ {file_path} (requerido)")
            success = False
    
    for file_path in optional_files:
        if Path(file_path).exists():
            print(f"   ✓ {file_path} (opcional)")
        else:
            print(f"   ⚠ {file_path} (opcional)")
    
    return success

def check_directories():
    """Verifica e cria diretórios necessários"""
    print("\n📂 Verificando diretórios...")
    
    directories = [
        "clips",
        "temp_videos",
        "logs"
    ]
    
    success = True
    
    for directory in directories:
        dir_path = Path(directory)
        if dir_path.exists():
            print(f"   ✓ {directory}/")
        else:
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                print(f"   ✓ {directory}/ (criado)")
            except Exception as e:
                print(f"   ✗ {directory}/ (erro: {e})")
                success = False
    
    return success

def check_config_file():
    """Verifica arquivo de configuração"""
    print("\n⚙️ Verificando configuração...")
    
    config_file = Path("config.env")
    if not config_file.exists():
        print("   ✗ config.env não encontrado")
        return False
    
    try:
        with open(config_file, 'r') as f:
            content = f.read()
        
        required_settings = [
            "CAMERA_1_URL",
            "CHUNK_DURATION",
            "BUFFER_SECONDS",
            "FINAL_CLIP_DURATION"
        ]
        
        success = True
        for setting in required_settings:
            if setting in content:
                print(f"   ✓ {setting}")
            else:
                print(f"   ✗ {setting} (requerido)")
                success = False
        
        # Verificar se há pelo menos uma URL de câmera configurada
        if "rtsp://" in content:
            print("   ✓ URL RTSP encontrada")
        else:
            print("   ⚠ Nenhuma URL RTSP configurada")
            print("     Configure CAMERA_1_URL, CAMERA_2_URL, etc.")
        
        return success
        
    except Exception as e:
        print(f"   ✗ Erro ao ler config.env: {e}")
        return False

def check_system_resources():
    """Verifica recursos do sistema"""
    print("\n💻 Verificando recursos do sistema...")
    
    try:
        import psutil
        
        # Memória
        memory = psutil.virtual_memory()
        memory_gb = memory.total / (1024**3)
        print(f"   ✓ RAM: {memory_gb:.1f} GB")
        
        if memory_gb < 2:
            print("     ⚠ RAM baixa (recomendado: >= 4GB)")
        
        # Espaço em disco
        disk = psutil.disk_usage('.')
        disk_free_gb = disk.free / (1024**3)
        print(f"   ✓ Espaço livre: {disk_free_gb:.1f} GB")
        
        if disk_free_gb < 5:
            print("     ⚠ Pouco espaço em disco (recomendado: >= 10GB)")
        
        # CPU
        cpu_count = psutil.cpu_count()
        print(f"   ✓ CPUs: {cpu_count}")
        
        return True
        
    except ImportError:
        print("   ⚠ psutil não disponível (instale: pip install psutil)")
        return True

def check_tmpfs():
    """Verifica disponibilidade de tmpfs (Linux)"""
    print("\n🚀 Verificando tmpfs...")
    
    if os.name != 'posix':
        print("   ⚠ Não é sistema Unix/Linux")
        print("     No Windows, será usado diretório temporário padrão")
        return True
    
    tmpfs_paths = ["/dev/shm", "/tmp"]
    
    for path in tmpfs_paths:
        if Path(path).exists():
            try:
                import psutil
                usage = psutil.disk_usage(path)
                size_gb = usage.total / (1024**3)
                
                if "shm" in path:
                    print(f"   ✓ {path} (tmpfs): {size_gb:.1f} GB")
                    if size_gb < 1:
                        print("     ⚠ tmpfs pequeno (recomendado: >= 2GB)")
                else:
                    print(f"   ✓ {path}: {size_gb:.1f} GB")
                
            except:
                print(f"   ✓ {path} (disponível)")
    
    return True

def run_basic_import_test():
    """Testa imports básicos do sistema"""
    print("\n🔧 Testando imports do sistema...")
    
    sys.path.insert(0, str(Path("src")))
    
    modules_to_test = [
        "config",
        "logger", 
        "buffer_manager",
        "rtsp_capture",
        "trigger_system",
        "clip_generator",
        "resilience_manager"
    ]
    
    success = True
    
    for module_name in modules_to_test:
        try:
            importlib.import_module(module_name)
            print(f"   ✓ {module_name}")
        except ImportError as e:
            print(f"   ✗ {module_name}: {e}")
            success = False
        except Exception as e:
            print(f"   ⚠ {module_name}: {e}")
    
    return success

def main():
    """Função principal de verificação"""
    print("Sistema de Buffer de Vídeo RTSP - Verificação de Sistema")
    print("=" * 60)
    
    checks = [
        ("Versão Python", check_python_version),
        ("Dependências Python", check_dependencies),
        ("FFmpeg", check_ffmpeg),
        ("Estrutura do Projeto", check_project_structure),
        ("Diretórios", check_directories),
        ("Arquivo de Configuração", check_config_file),
        ("Recursos do Sistema", check_system_resources),
        ("tmpfs/RAM", check_tmpfs),
        ("Imports do Sistema", run_basic_import_test)
    ]
    
    results = []
    
    for check_name, check_func in checks:
        try:
            result = check_func()
            results.append((check_name, result))
        except Exception as e:
            print(f"\n❌ Erro em {check_name}: {e}")
            results.append((check_name, False))
    
    # Resumo final
    print("\n" + "=" * 60)
    print("RESUMO DA VERIFICAÇÃO")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for check_name, result in results:
        status = "✅ PASSOU" if result else "❌ FALHOU"
        print(f"{check_name:.<30} {status}")
    
    print(f"\nResultado: {passed}/{total} verificações passaram")
    
    if passed == total:
        print("\n🎉 SISTEMA PRONTO PARA USO!")
        print("\nPróximos passos:")
        print("1. Configure as URLs das câmeras em config.env")
        print("2. Execute: python main.py")
        print("3. Ou use os scripts: bash scripts/test-cameras.sh")
    elif passed >= total - 2:
        print("\n⚠️ SISTEMA QUASE PRONTO")
        print("Corrija os problemas identificados acima")
    else:
        print("\n❌ SISTEMA NÃO ESTÁ PRONTO")
        print("Múltiplos problemas identificados - consulte README.txt")
    
    return passed == total

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nVerificação interrompida pelo usuário")
        sys.exit(1)
    except Exception as e:
        print(f"\nErro inesperado: {e}")
        sys.exit(1)
