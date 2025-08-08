"""
Módulo de logging estruturado para o sistema de buffer de vídeo RTSP.
Suporte para logs em JSON e formato texto, com diferentes níveis.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from logging.handlers import RotatingFileHandler

class JSONFormatter(logging.Formatter):
    """Formatter para logs em formato JSON"""
    
    def format(self, record: logging.LogRecord) -> str:
        """Formata o log em JSON"""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Adicionar informações extras se disponíveis
        if hasattr(record, 'camera_id'):
            log_data['camera_id'] = record.camera_id
        
        if hasattr(record, 'event_type'):
            log_data['event_type'] = record.event_type
        
        if hasattr(record, 'extra_data'):
            log_data['extra_data'] = record.extra_data
        
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)

class SystemLogger:
    """Classe para gerenciar logging do sistema"""
    
    def __init__(self, config):
        """
        Inicializa o sistema de logging
        
        Args:
            config: Instância da classe Config
        """
        self.config = config
        self.loggers = {}
        self._setup_logging()
    
    def _setup_logging(self):
        """Configura o sistema de logging"""
        # Configurar nível de log
        log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        
        # Configurar formatters
        if self.config.log_format.lower() == "json":
            formatter = JSONFormatter()
        else:
            formatter = logging.Formatter(
                fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        
        # Configurar handler para console
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level)
        
        # Configurar handler para arquivo (logs rotativos)
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        file_handler = RotatingFileHandler(
            log_dir / "system.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        
        # Configurar logger raiz
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)
        
        # Suprimir logs verbose de bibliotecas externas
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('requests').setLevel(logging.WARNING)
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        Retorna um logger específico
        
        Args:
            name: Nome do logger
            
        Returns:
            Logger configurado
        """
        if name not in self.loggers:
            self.loggers[name] = logging.getLogger(name)
        
        return self.loggers[name]
    
    def log_camera_event(self, camera_id: str, event_type: str, message: str, 
                        extra_data: Optional[Dict[str, Any]] = None, 
                        level: str = "INFO"):
        """
        Log específico para eventos de câmera
        
        Args:
            camera_id: ID da câmera
            event_type: Tipo do evento (segment_created, segment_removed, etc.)
            message: Mensagem do log
            extra_data: Dados extras para incluir no log
            level: Nível do log
        """
        logger = self.get_logger(f"camera.{camera_id}")
        log_level = getattr(logging, level.upper(), logging.INFO)
        
        # Criar record customizado
        record = logger.makeRecord(
            logger.name, log_level, "", 0, message, (), None
        )
        record.camera_id = camera_id
        record.event_type = event_type
        if extra_data:
            record.extra_data = extra_data
        
        logger.handle(record)
    
    def log_system_event(self, event_type: str, message: str, 
                        extra_data: Optional[Dict[str, Any]] = None,
                        level: str = "INFO"):
        """
        Log específico para eventos do sistema
        
        Args:
            event_type: Tipo do evento (startup, shutdown, error, etc.)
            message: Mensagem do log
            extra_data: Dados extras para incluir no log
            level: Nível do log
        """
        logger = self.get_logger("system")
        log_level = getattr(logging, level.upper(), logging.INFO)
        
        record = logger.makeRecord(
            logger.name, log_level, "", 0, message, (), None
        )
        record.event_type = event_type
        if extra_data:
            record.extra_data = extra_data
        
        logger.handle(record)
    
    def log_buffer_event(self, camera_id: str, event_type: str, filename: str,
                        extra_data: Optional[Dict[str, Any]] = None):
        """
        Log específico para eventos de buffer
        
        Args:
            camera_id: ID da câmera
            event_type: Tipo do evento (chunk_created, chunk_removed, buffer_full)
            filename: Nome do arquivo envolvido
            extra_data: Dados extras
        """
        message = f"Buffer event: {event_type} - {filename}"
        buffer_data = {"filename": filename}
        if extra_data:
            buffer_data.update(extra_data)
        
        self.log_camera_event(camera_id, event_type, message, buffer_data)
    
    def log_clip_event(self, camera_id: str, clip_filename: str, 
                      trigger_time: datetime, duration: float,
                      source_chunks: list):
        """
        Log específico para geração de clipes
        
        Args:
            camera_id: ID da câmera
            clip_filename: Nome do arquivo do clipe gerado
            trigger_time: Momento do gatilho
            duration: Duração do clipe
            source_chunks: Lista de chunks utilizados
        """
        message = f"Clipe gerado: {clip_filename}"
        clip_data = {
            "clip_filename": clip_filename,
            "trigger_time": trigger_time.isoformat(),
            "duration_seconds": duration,
            "source_chunks": source_chunks,
            "chunks_count": len(source_chunks)
        }
        
        self.log_camera_event(camera_id, "clip_generated", message, clip_data)
    
    def log_reconnection_event(self, camera_id: str, attempt: int, 
                             max_attempts: int, delay: float):
        """
        Log específico para eventos de reconexão
        
        Args:
            camera_id: ID da câmera
            attempt: Tentativa atual
            max_attempts: Máximo de tentativas
            delay: Delay antes da próxima tentativa
        """
        message = f"Tentativa de reconexão {attempt}/{max_attempts} em {delay}s"
        reconnect_data = {
            "attempt": attempt,
            "max_attempts": max_attempts,
            "delay_seconds": delay
        }
        
        self.log_camera_event(camera_id, "reconnection_attempt", message, 
                             reconnect_data, "WARNING")
    
    def log_error(self, component: str, error: Exception, 
                  extra_data: Optional[Dict[str, Any]] = None):
        """
        Log específico para erros
        
        Args:
            component: Componente onde ocorreu o erro
            error: Exceção capturada
            extra_data: Dados extras sobre o erro
        """
        logger = self.get_logger(f"error.{component}")
        
        error_data = {
            "error_type": type(error).__name__,
            "error_message": str(error)
        }
        if extra_data:
            error_data.update(extra_data)
        
        record = logger.makeRecord(
            logger.name, logging.ERROR, "", 0, f"Erro em {component}: {error}", (), 
            (type(error), error, error.__traceback__)
        )
        record.event_type = "error"
        record.extra_data = error_data
        
        logger.handle(record)
