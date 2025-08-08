"""
Script principal do sistema de buffer de vídeo RTSP.
Orquestra todos os componentes e gerencia o ciclo de vida da aplicação.
"""

import signal
import sys
import time
import threading
from pathlib import Path
from datetime import datetime

# Importar módulos do sistema
from config import Config
from logger import SystemLogger
from buffer_manager import BufferManager
from rtsp_capture import RTSPCaptureManager
from trigger_system import TriggerSystem
from clip_generator import ClipGenerator
from resilience_manager import ResilienceManager

class VideoBufferSystem:
    """
    Classe principal que gerencia todo o sistema de buffer de vídeo.
    """
    
    def __init__(self, config_file: str = "config.env"):
        """
        Inicializa o sistema
        
        Args:
            config_file: Caminho para o arquivo de configuração
        """
        self.config_file = config_file
        self.is_running = False
        self.shutdown_event = threading.Event()
        
        # Componentes do sistema
        self.config: Config = None
        self.logger: SystemLogger = None
        self.buffer_manager: BufferManager = None
        self.capture_manager: RTSPCaptureManager = None
        self.clip_generator: ClipGenerator = None
        self.trigger_system: TriggerSystem = None
        self.resilience_manager: ResilienceManager = None
        
        # Registrar handlers de sinal
        self._register_signal_handlers()
    
    def _register_signal_handlers(self):
        """Registra handlers para sinais do sistema"""
        def signal_handler(signum, frame):
            print(f"\nSinal {signum} recebido. Iniciando shutdown...")
            self.shutdown()
        
        signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # Termination
        
        # No Windows, SIGBREAK é equivalente ao Ctrl+Break
        if hasattr(signal, 'SIGBREAK'):
            signal.signal(signal.SIGBREAK, signal_handler)
    
    def initialize(self) -> bool:
        """
        Inicializa todos os componentes do sistema
        
        Returns:
            True se inicializado com sucesso
        """
        try:
            print("Inicializando Sistema de Buffer de Vídeo RTSP...")
            print("="*60)
            
            # 1. Carregar configurações
            print("1. Carregando configurações...")
            self.config = Config(self.config_file)
            print(f"   ✓ {len(self.config.camera_urls)} câmeras configuradas")
            print(f"   ✓ Buffer: {self.config.buffer_seconds}s, Clipes: {self.config.final_clip_duration}s")
            
            # 2. Inicializar logging
            print("2. Inicializando sistema de logging...")
            self.logger = SystemLogger(self.config)
            print(f"   ✓ Logs em formato {self.config.log_format}, nível {self.config.log_level}")
            
            self.logger.log_system_event(
                "system_initialization_started",
                "Inicializando sistema de buffer de vídeo",
                {"config_file": self.config_file}
            )
            
            # 3. Inicializar gerenciador de buffers
            print("3. Inicializando gerenciador de buffers...")
            self.buffer_manager = BufferManager(self.config, self.logger)
            print(f"   ✓ Buffers criados em {self.config.temp_dir}")
            
            # 4. Inicializar gerador de clipes
            print("4. Inicializando gerador de clipes...")
            self.clip_generator = ClipGenerator(self.config, self.logger, self.buffer_manager)
            print(f"   ✓ Clipes serão salvos em {self.config.clips_dir}")
            
            # 5. Inicializar gerenciador de capturas RTSP
            print("5. Inicializando capturas RTSP...")
            self.capture_manager = RTSPCaptureManager(
                self.config, self.logger, self.buffer_manager
            )
            print(f"   ✓ Capturas configuradas para {len(self.config.camera_urls)} câmeras")
            
            # 6. Inicializar sistema de gatilhos
            print("6. Inicializando sistema de gatilhos...")
            self.trigger_system = TriggerSystem(
                self.config, self.logger, self.clip_generator
            )
            print(f"   ✓ Modo de gatilho: {self.config.trigger_mode}")
            
            # 7. Inicializar gerenciador de resiliência
            print("7. Inicializando sistema de resiliência...")
            self.resilience_manager = ResilienceManager(
                self.config, self.logger, self.capture_manager, self.buffer_manager
            )
            print("   ✓ Monitoramento de saúde configurado")
            
            print("="*60)
            print("✓ SISTEMA INICIALIZADO COM SUCESSO")
            print("="*60)
            
            self.logger.log_system_event(
                "system_initialization_completed",
                "Sistema inicializado com sucesso"
            )
            
            return True
            
        except Exception as e:
            print(f"✗ ERRO NA INICIALIZAÇÃO: {e}")
            if self.logger:
                self.logger.log_error("system_initialization", e)
            return False
    
    def start(self) -> bool:
        """
        Inicia todos os componentes do sistema
        
        Returns:
            True se iniciado com sucesso
        """
        try:
            if not self.initialize():
                return False
            
            print("\nIniciando componentes do sistema...")
            
            # 1. Iniciar monitoramento de resiliência
            print("1. Iniciando monitoramento de resiliência...")
            self.resilience_manager.start_monitoring()
            
            # 2. Iniciar capturas RTSP
            print("2. Iniciando capturas RTSP...")
            if not self.capture_manager.start_all_captures():
                print("   ⚠ Algumas capturas falharam ao iniciar")
            else:
                print("   ✓ Todas as capturas iniciadas")
            
            # Aguardar um pouco para as capturas estabilizarem
            print("3. Aguardando estabilização das capturas...")
            time.sleep(5)
            
            # 3. Iniciar sistema de gatilhos
            print("4. Iniciando sistema de gatilhos...")
            self.trigger_system.start()
            
            self.is_running = True
            
            print("\n" + "="*60)
            print("🎥 SISTEMA DE CAPTURA INICIADO COM SUCESSO!")
            print("="*60)
            
            # Mostrar informações de status
            self._show_status_info()
            
            self.logger.log_system_event(
                "system_startup_completed",
                "Sistema iniciado e operacional"
            )
            
            return True
            
        except Exception as e:
            print(f"✗ ERRO AO INICIAR SISTEMA: {e}")
            if self.logger:
                self.logger.log_error("system_startup", e)
            return False
    
    def _show_status_info(self):
        """Mostra informações de status do sistema"""
        print("\n📊 STATUS DO SISTEMA:")
        print("-" * 30)
        
        # Status das capturas
        captures_info = self.capture_manager.get_all_captures_info()
        for camera_id, info in captures_info.items():
            status = "🟢 RODANDO" if info["is_running"] else "🔴 PARADO"
            print(f"   {camera_id}: {status}")
        
        # Status dos buffers
        buffers_info = self.buffer_manager.get_all_buffers_info()
        total_segments = sum(info["segments_count"] for info in buffers_info.values())
        print(f"   Buffer: {total_segments} segmentos ativos")
        
        # Informações de controle
        print("\n🎮 CONTROLES:")
        print("-" * 30)
        if self.config.trigger_mode == "keyboard":
            print("   's' + ENTER: Salvar clipe")
            print("   'q' + ENTER: Sair")
        elif self.config.trigger_mode == "http":
            print(f"   POST http://localhost:{self.config.http_port}/save-clip")
            print(f"   GET  http://localhost:{self.config.http_port}/status")
        
        print("\n📁 DIRETÓRIOS:")
        print("-" * 30)
        print(f"   Buffer temporário: {self.config.temp_dir}")
        print(f"   Clipes salvos: {self.config.clips_dir}")
        
        print()
    
    def run(self):
        """
        Loop principal do sistema
        """
        if not self.start():
            sys.exit(1)
        
        try:
            # Loop principal - aguardar sinal de shutdown
            while self.is_running and not self.shutdown_event.is_set():
                # Verificar se alguma captura crítica falhou
                self._check_critical_failures()
                
                # Aguardar um pouco antes da próxima verificação
                if self.shutdown_event.wait(timeout=30):  # 30 segundos
                    break
            
        except KeyboardInterrupt:
            print("\nInterrompido pelo usuário...")
        
        except Exception as e:
            print(f"\nErro no loop principal: {e}")
            if self.logger:
                self.logger.log_error("main_loop", e)
        
        finally:
            self.shutdown()
    
    def _check_critical_failures(self):
        """Verifica falhas críticas no sistema"""
        try:
            if not self.resilience_manager:
                return
            
            health = self.resilience_manager.get_system_health_summary()
            
            # Se muitos componentes falharam, pode ser necessário reiniciar
            failed_count = health["summary"]["failed_components"]
            critical_count = health["summary"]["critical_components"]
            total_count = health["summary"]["total_components"]
            
            if failed_count > 0 or critical_count > 1:
                self.logger.log_system_event(
                    "system_degraded",
                    f"Sistema degradado: {failed_count} falhas, {critical_count} críticos",
                    {
                        "failed_components": failed_count,
                        "critical_components": critical_count,
                        "total_components": total_count
                    },
                    level="WARNING"
                )
                
                # Tentar recuperação automática
                if failed_count > 0:
                    self.resilience_manager.force_recovery_all()
            
        except Exception as e:
            if self.logger:
                self.logger.log_error("critical_check", e)
    
    def shutdown(self):
        """
        Para todos os componentes do sistema de forma ordenada
        """
        if not self.is_running:
            return
        
        print("\n🛑 PARANDO SISTEMA...")
        print("="*40)
        
        self.is_running = False
        self.shutdown_event.set()
        
        try:
            if self.logger:
                self.logger.log_system_event(
                    "system_shutdown_started",
                    "Iniciando shutdown do sistema"
                )
            
            # 1. Parar sistema de gatilhos
            if self.trigger_system:
                print("1. Parando sistema de gatilhos...")
                self.trigger_system.stop()
            
            # 2. Parar capturas RTSP
            if self.capture_manager:
                print("2. Parando capturas RTSP...")
                self.capture_manager.stop_all_captures()
            
            # 3. Parar monitoramento de resiliência
            if self.resilience_manager:
                print("3. Parando monitoramento...")
                self.resilience_manager.stop_monitoring()
            
            # 4. Limpar buffers (opcional - manter para debug)
            # if self.buffer_manager:
            #     print("4. Limpando buffers...")
            #     self.buffer_manager.clear_all_buffers()
            
            print("4. Finalizando logs...")
            
            if self.logger:
                # Mostrar estatísticas finais
                if self.clip_generator:
                    stats = self.clip_generator.get_generation_stats()
                    self.logger.log_system_event(
                        "final_statistics",
                        f"Clipes gerados: {stats['clips_generated']}",
                        stats
                    )
                
                self.logger.log_system_event(
                    "system_shutdown_completed",
                    "Sistema finalizado com sucesso"
                )
            
            print("✓ SISTEMA PARADO COM SUCESSO")
            
        except Exception as e:
            print(f"✗ Erro durante shutdown: {e}")
            if self.logger:
                self.logger.log_error("system_shutdown", e)
    
    def get_status(self) -> dict:
        """
        Retorna status completo do sistema
        
        Returns:
            Dicionário com status de todos os componentes
        """
        if not self.is_running:
            return {"status": "stopped"}
        
        try:
            status = {
                "status": "running",
                "timestamp": datetime.utcnow().isoformat(),
                "uptime_seconds": (datetime.utcnow() - datetime.utcnow()).total_seconds()
            }
            
            if self.capture_manager:
                status["captures"] = self.capture_manager.get_all_captures_info()
            
            if self.buffer_manager:
                status["buffers"] = self.buffer_manager.get_all_buffers_info()
            
            if self.clip_generator:
                status["clip_generator"] = self.clip_generator.get_generation_stats()
            
            if self.resilience_manager:
                status["health"] = self.resilience_manager.get_system_health_summary()
            
            return status
            
        except Exception as e:
            if self.logger:
                self.logger.log_error("status_request", e)
            return {"status": "error", "error": str(e)}

def main():
    """Função principal"""
    print("Sistema de Buffer de Vídeo RTSP v1.0")
    print("Raspberry Pi - Windows - Linux")
    print("="*60)
    
    # Verificar se arquivo de configuração existe
    config_file = "config.env"
    if not Path(config_file).exists():
        print(f"✗ Arquivo de configuração não encontrado: {config_file}")
        print("   Crie o arquivo config.env com as configurações necessárias")
        sys.exit(1)
    
    # Criar e executar sistema
    system = VideoBufferSystem(config_file)
    
    try:
        system.run()
    except Exception as e:
        print(f"\n✗ ERRO FATAL: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()