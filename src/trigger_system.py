"""
Sistema de gatilho para salvar clipes de vídeo.
Suporte para gatilho via teclado (tecla 's') e HTTP endpoint.
"""

import threading
import time
import sys
import select
import queue
from datetime import datetime
from typing import Optional, Callable, Dict, Any
from pathlib import Path
import platform

# Importações condicionais para HTTP server
try:
    from flask import Flask, request, jsonify
    from werkzeug.serving import make_server
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

# Importações específicas do Windows para detecção de tecla
if platform.system() == "Windows":
    try:
        import msvcrt
        WINDOWS_KEYBOARD_AVAILABLE = True
    except ImportError:
        WINDOWS_KEYBOARD_AVAILABLE = False
else:
    WINDOWS_KEYBOARD_AVAILABLE = False

class KeyboardTrigger:
    """
    Gatilho via teclado (tecla 's' para salvar).
    """
    
    def __init__(self, trigger_callback: Callable, logger):
        """
        Inicializa o gatilho de teclado
        
        Args:
            trigger_callback: Função chamada quando o gatilho é acionado
            logger: Logger para eventos
        """
        self.trigger_callback = trigger_callback
        self.logger = logger
        self.is_running = False
        self.keyboard_thread: Optional[threading.Thread] = None
    
    def start(self):
        """Inicia o monitoramento do teclado"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # Verificar se podemos usar detecção de teclado
        if platform.system() == "Windows" and WINDOWS_KEYBOARD_AVAILABLE:
            self.keyboard_thread = threading.Thread(
                target=self._windows_keyboard_worker,
                name="KeyboardTrigger",
                daemon=True
            )
        else:
            self.keyboard_thread = threading.Thread(
                target=self._unix_keyboard_worker,
                name="KeyboardTrigger",
                daemon=True
            )
        
        self.keyboard_thread.start()
        
        self.logger.log_system_event(
            "keyboard_trigger_started",
            "Gatilho de teclado iniciado. Pressione 's' para salvar clipe."
        )
        
        # Mostrar instruções no console
        print("\n" + "="*60)
        print("SISTEMA DE CAPTURA DE VÍDEO INICIADO")
        print("="*60)
        print("Pressione 's' + ENTER para salvar um clipe de vídeo")
        print("Pressione 'q' + ENTER para sair")
        print("="*60 + "\n")
    
    def _windows_keyboard_worker(self):
        """Worker para detecção de teclado no Windows"""
        while self.is_running:
            try:
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode('utf-8').lower()
                    
                    if key == 's':
                        self._trigger_save()
                    elif key == 'q':
                        self._trigger_quit()
                
                time.sleep(0.1)
                
            except Exception as e:
                self.logger.log_error("keyboard_trigger", e)
                time.sleep(1)
    
    def _unix_keyboard_worker(self):
        """Worker para detecção de teclado no Unix/Linux"""
        while self.is_running:
            try:
                # Verificar se há entrada disponível no stdin
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    line = sys.stdin.readline().strip().lower()
                    
                    if line == 's':
                        self._trigger_save()
                    elif line == 'q' or line == 'quit' or line == 'exit':
                        self._trigger_quit()
                
            except Exception as e:
                self.logger.log_error("keyboard_trigger", e)
                time.sleep(1)
    
    def _trigger_save(self):
        """Aciona o gatilho para salvar clipe"""
        trigger_time = datetime.utcnow()
        
        self.logger.log_system_event(
            "manual_trigger",
            "Gatilho acionado via teclado",
            {"trigger_time": trigger_time.isoformat()}
        )
        
        print(f"\n[{trigger_time.strftime('%H:%M:%S')}] Salvando clipe...")
        
        try:
            result = self.trigger_callback(trigger_time, "keyboard")
            if result:
                print("✓ Clipe salvo com sucesso!")
            else:
                print("✗ Erro ao salvar clipe")
        except Exception as e:
            self.logger.log_error("trigger_callback", e)
            print("✗ Erro ao processar gatilho")
    
    def _trigger_quit(self):
        """Aciona saída do sistema"""
        self.logger.log_system_event(
            "quit_requested",
            "Saída solicitada via teclado"
        )
        print("\nEncerrando sistema...")
        self.stop()
        
        # Sinal para o sistema principal parar
        import os
        os._exit(0)
    
    def stop(self):
        """Para o monitoramento do teclado"""
        self.is_running = False
        
        if self.keyboard_thread and self.keyboard_thread.is_alive():
            self.keyboard_thread.join(timeout=2)
        
        self.logger.log_system_event(
            "keyboard_trigger_stopped",
            "Gatilho de teclado parado"
        )

class HTTPTrigger:
    """
    Gatilho via HTTP endpoint.
    """
    
    def __init__(self, trigger_callback: Callable, config, logger):
        """
        Inicializa o gatilho HTTP
        
        Args:
            trigger_callback: Função chamada quando o gatilho é acionado
            config: Configurações do sistema
            logger: Logger para eventos
        """
        if not FLASK_AVAILABLE:
            raise ImportError("Flask não está disponível. Instale com: pip install flask")
        
        self.trigger_callback = trigger_callback
        self.config = config
        self.logger = logger
        
        # Configurar Flask app
        self.app = Flask(__name__)
        self.app.config['JSON_AS_ASCII'] = False
        
        # Registrar rotas
        self._register_routes()
        
        # Servidor HTTP
        self.server: Optional = None
        self.is_running = False
    
    def _register_routes(self):
        """Registra as rotas HTTP"""
        
        @self.app.route('/save-clip', methods=['POST'])
        def save_clip():
            """Endpoint para salvar clipe"""
            try:
                trigger_time = datetime.utcnow()
                
                # Dados opcionais do request
                data = request.get_json() or {}
                camera_id = data.get('camera_id', 'all')
                duration = data.get('duration', self.config.final_clip_duration)
                
                self.logger.log_system_event(
                    "http_trigger",
                    f"Gatilho acionado via HTTP para câmera {camera_id}",
                    {
                        "trigger_time": trigger_time.isoformat(),
                        "camera_id": camera_id,
                        "duration": duration,
                        "client_ip": request.remote_addr
                    }
                )
                
                # Chamar callback
                result = self.trigger_callback(trigger_time, "http", {
                    "camera_id": camera_id,
                    "duration": duration
                })
                
                if result:
                    return jsonify({
                        "success": True,
                        "message": "Clipe salvo com sucesso",
                        "trigger_time": trigger_time.isoformat(),
                        "camera_id": camera_id
                    })
                else:
                    return jsonify({
                        "success": False,
                        "message": "Erro ao salvar clipe"
                    }), 500
                
            except Exception as e:
                self.logger.log_error("http_trigger", e, {
                    "client_ip": request.remote_addr
                })
                return jsonify({
                    "success": False,
                    "message": f"Erro interno: {str(e)}"
                }), 500
        
        @self.app.route('/status', methods=['GET'])
        def get_status():
            """Endpoint para verificar status do sistema"""
            try:
                # Aqui poderia retornar informações do sistema
                return jsonify({
                    "status": "running",
                    "timestamp": datetime.utcnow().isoformat(),
                    "cameras_count": len(self.config.camera_urls),
                    "buffer_duration": self.config.buffer_seconds,
                    "clip_duration": self.config.final_clip_duration
                })
            except Exception as e:
                self.logger.log_error("status_endpoint", e)
                return jsonify({
                    "status": "error",
                    "message": str(e)
                }), 500
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Endpoint de health check"""
            return jsonify({"status": "healthy"})
        
        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({
                "error": "Endpoint não encontrado",
                "available_endpoints": [
                    "POST /save-clip - Salvar clipe de vídeo",
                    "GET /status - Status do sistema",
                    "GET /health - Health check"
                ]
            }), 404
    
    def start(self):
        """Inicia o servidor HTTP"""
        if self.is_running:
            return
        
        try:
            # Criar servidor
            self.server = make_server(
                host='0.0.0.0',
                port=self.config.http_port,
                app=self.app,
                threaded=True
            )
            
            self.is_running = True
            
            # Iniciar servidor em thread separada
            server_thread = threading.Thread(
                target=self.server.serve_forever,
                name="HTTPTrigger",
                daemon=True
            )
            server_thread.start()
            
            self.logger.log_system_event(
                "http_trigger_started",
                f"Servidor HTTP iniciado na porta {self.config.http_port}",
                {"port": self.config.http_port}
            )
            
            print(f"Servidor HTTP iniciado em http://0.0.0.0:{self.config.http_port}")
            print(f"Endpoint para salvar clipes: POST /save-clip")
            
        except Exception as e:
            self.logger.log_error("http_trigger_start", e)
            self.is_running = False
            raise
    
    def stop(self):
        """Para o servidor HTTP"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self.server:
            self.server.shutdown()
        
        self.logger.log_system_event(
            "http_trigger_stopped",
            "Servidor HTTP parado"
        )

class TriggerSystem:
    """
    Sistema principal de gatilhos que gerencia keyboard e HTTP.
    """
    
    def __init__(self, config, logger, clip_generator):
        """
        Inicializa o sistema de gatilhos
        
        Args:
            config: Configurações do sistema
            logger: Logger para eventos
            clip_generator: Gerador de clipes
        """
        self.config = config
        self.logger = logger
        self.clip_generator = clip_generator
        
        # Filas para comunicação entre threads
        self.trigger_queue = queue.Queue()
        
        # Gatilhos
        self.keyboard_trigger: Optional[KeyboardTrigger] = None
        self.http_trigger: Optional[HTTPTrigger] = None
        
        # Worker thread
        self.worker_thread: Optional[threading.Thread] = None
        self.is_running = False
    
    def _trigger_callback(self, trigger_time: datetime, source: str, extra_data: Dict = None):
        """
        Callback chamado quando um gatilho é acionado
        
        Args:
            trigger_time: Momento do gatilho
            source: Fonte do gatilho (keyboard/http)
            extra_data: Dados extras do gatilho
            
        Returns:
            True se processado com sucesso
        """
        try:
            # Adicionar à fila para processamento
            self.trigger_queue.put({
                "trigger_time": trigger_time,
                "source": source,
                "extra_data": extra_data or {}
            })
            
            return True
            
        except Exception as e:
            self.logger.log_error("trigger_callback", e)
            return False
    
    def _trigger_worker(self):
        """Worker thread que processa gatilhos da fila"""
        while self.is_running:
            try:
                # Aguardar gatilho na fila (timeout para permitir verificação de is_running)
                trigger_data = self.trigger_queue.get(timeout=1)
                
                # Processar gatilho
                self._process_trigger(trigger_data)
                
                self.trigger_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.log_error("trigger_worker", e)
                time.sleep(1)
    
    def _process_trigger(self, trigger_data: Dict):
        """
        Processa um gatilho específico
        
        Args:
            trigger_data: Dados do gatilho
        """
        try:
            trigger_time = trigger_data["trigger_time"]
            source = trigger_data["source"]
            extra_data = trigger_data["extra_data"]
            
            # Determinar quais câmeras processar
            camera_id = extra_data.get("camera_id", "all")
            duration = extra_data.get("duration", self.config.final_clip_duration)
            
            if camera_id == "all":
                # Processar todas as câmeras
                cameras_to_process = list(self.config.get_all_cameras_info())
            else:
                # Processar câmera específica
                try:
                    camera_info = self.config.get_camera_info(int(camera_id.replace("camera_", "")) - 1)
                    cameras_to_process = [camera_info]
                except (ValueError, IndexError):
                    self.logger.log_system_event(
                        "invalid_camera_id",
                        f"ID de câmera inválido: {camera_id}",
                        level="ERROR"
                    )
                    return
            
            # Gerar clipes para cada câmera
            success_count = 0
            total_cameras = len(cameras_to_process)
            
            for camera_info in cameras_to_process:
                try:
                    success = self.clip_generator.generate_clip(
                        camera_id=camera_info["name"],
                        trigger_time=trigger_time,
                        duration=duration
                    )
                    
                    if success:
                        success_count += 1
                    
                except Exception as e:
                    self.logger.log_error("clip_generation", e, {
                        "camera_id": camera_info["name"],
                        "trigger_time": trigger_time.isoformat()
                    })
            
            # Log do resultado
            self.logger.log_system_event(
                "trigger_processed",
                f"Gatilho processado: {success_count}/{total_cameras} clipes gerados",
                {
                    "source": source,
                    "trigger_time": trigger_time.isoformat(),
                    "success_count": success_count,
                    "total_cameras": total_cameras,
                    "duration": duration
                }
            )
            
        except Exception as e:
            self.logger.log_error("process_trigger", e, trigger_data)
    
    def start(self):
        """Inicia o sistema de gatilhos"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # Iniciar worker thread
        self.worker_thread = threading.Thread(
            target=self._trigger_worker,
            name="TriggerWorker",
            daemon=True
        )
        self.worker_thread.start()
        
        # Iniciar gatilho apropriado baseado na configuração
        if self.config.trigger_mode == "keyboard":
            self.keyboard_trigger = KeyboardTrigger(self._trigger_callback, self.logger)
            self.keyboard_trigger.start()
            
        elif self.config.trigger_mode == "http":
            if not FLASK_AVAILABLE:
                self.logger.log_system_event(
                    "http_trigger_unavailable",
                    "Flask não disponível. Usando gatilho de teclado como fallback.",
                    level="WARNING"
                )
                self.keyboard_trigger = KeyboardTrigger(self._trigger_callback, self.logger)
                self.keyboard_trigger.start()
            else:
                self.http_trigger = HTTPTrigger(self._trigger_callback, self.config, self.logger)
                self.http_trigger.start()
                
                # Também habilitar teclado para controle local
                self.keyboard_trigger = KeyboardTrigger(self._trigger_callback, self.logger)
                self.keyboard_trigger.start()
        
        self.logger.log_system_event(
            "trigger_system_started",
            f"Sistema de gatilhos iniciado em modo {self.config.trigger_mode}"
        )
    
    def stop(self):
        """Para o sistema de gatilhos"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # Parar gatilhos
        if self.keyboard_trigger:
            self.keyboard_trigger.stop()
        
        if self.http_trigger:
            self.http_trigger.stop()
        
        # Aguardar worker thread
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5)
        
        self.logger.log_system_event(
            "trigger_system_stopped",
            "Sistema de gatilhos parado"
        )
