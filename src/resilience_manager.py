"""
Sistema de resiliência e reconexão automática para o sistema de captura RTSP.
Monitora a saúde dos componentes e gerencia recuperação automática.
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
from dataclasses import dataclass, field
import psutil
import platform

class ComponentStatus(Enum):
    """Status dos componentes do sistema"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    FAILED = "failed"
    RECOVERING = "recovering"

@dataclass
class HealthMetrics:
    """Métricas de saúde de um componente"""
    status: ComponentStatus
    last_check: datetime
    uptime_seconds: float
    error_count: int = 0
    warning_count: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    custom_metrics: Dict[str, Any] = field(default_factory=dict)

class ComponentMonitor:
    """
    Monitor para um componente específico do sistema.
    """
    
    def __init__(self, component_name: str, check_interval: float, 
                 health_check_func: Callable, logger):
        """
        Inicializa o monitor de componente
        
        Args:
            component_name: Nome do componente
            check_interval: Intervalo entre verificações em segundos
            health_check_func: Função que verifica a saúde do componente
            logger: Logger para eventos
        """
        self.component_name = component_name
        self.check_interval = check_interval
        self.health_check_func = health_check_func
        self.logger = logger
        
        # Estado do monitor
        self.is_running = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # Métricas
        self.metrics = HealthMetrics(
            status=ComponentStatus.HEALTHY,
            last_check=datetime.utcnow(),
            uptime_seconds=0
        )
        
        # Histórico de status
        self.status_history: List[tuple] = []  # (timestamp, status)
        self.max_history_entries = 100
        
        # Callbacks
        self.status_change_callbacks: List[Callable] = []
        
        self.start_time = datetime.utcnow()
    
    def add_status_change_callback(self, callback: Callable):
        """Adiciona callback para mudanças de status"""
        self.status_change_callbacks.append(callback)
    
    def start_monitoring(self):
        """Inicia o monitoramento do componente"""
        if self.is_running:
            return
        
        self.is_running = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_worker,
            name=f"Monitor-{self.component_name}",
            daemon=True
        )
        self.monitor_thread.start()
        
        self.logger.log_system_event(
            "component_monitor_started",
            f"Monitor iniciado para {self.component_name}",
            {"component": self.component_name, "interval": self.check_interval}
        )
    
    def stop_monitoring(self):
        """Para o monitoramento do componente"""
        self.is_running = False
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        
        self.logger.log_system_event(
            "component_monitor_stopped",
            f"Monitor parado para {self.component_name}",
            {"component": self.component_name}
        )
    
    def _monitor_worker(self):
        """Worker thread que executa as verificações de saúde"""
        while self.is_running:
            try:
                # Executar verificação de saúde
                old_status = self.metrics.status
                self._perform_health_check()
                
                # Verificar se houve mudança de status
                if self.metrics.status != old_status:
                    self._on_status_change(old_status, self.metrics.status)
                
                # Aguardar próxima verificação
                time.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.log_error("component_monitor", e, {
                    "component": self.component_name
                })
                time.sleep(self.check_interval)
    
    def _perform_health_check(self):
        """Executa verificação de saúde do componente"""
        try:
            # Chamar função de verificação
            check_result = self.health_check_func()
            
            # Atualizar métricas
            self.metrics.last_check = datetime.utcnow()
            self.metrics.uptime_seconds = (
                self.metrics.last_check - self.start_time
            ).total_seconds()
            
            # Processar resultado
            if isinstance(check_result, dict):
                self.metrics.status = check_result.get('status', ComponentStatus.HEALTHY)
                self.metrics.custom_metrics.update(
                    check_result.get('metrics', {})
                )
                
                # Verificar se há erro reportado
                if 'error' in check_result:
                    self.metrics.error_count += 1
                    self.metrics.last_error = str(check_result['error'])
                    self.metrics.last_error_time = datetime.utcnow()
                
                # Verificar se há warning reportado
                if 'warning' in check_result:
                    self.metrics.warning_count += 1
                    
            elif isinstance(check_result, ComponentStatus):
                self.metrics.status = check_result
            else:
                # Assumir healthy se retornou True ou similar
                self.metrics.status = (
                    ComponentStatus.HEALTHY if check_result 
                    else ComponentStatus.FAILED
                )
            
        except Exception as e:
            # Erro na verificação de saúde
            self.metrics.status = ComponentStatus.FAILED
            self.metrics.error_count += 1
            self.metrics.last_error = str(e)
            self.metrics.last_error_time = datetime.utcnow()
            self.metrics.last_check = datetime.utcnow()
            
            self.logger.log_error("health_check", e, {
                "component": self.component_name
            })
    
    def _on_status_change(self, old_status: ComponentStatus, new_status: ComponentStatus):
        """Chamado quando há mudança de status"""
        # Adicionar ao histórico
        self.status_history.append((datetime.utcnow(), new_status))
        
        # Manter tamanho do histórico
        if len(self.status_history) > self.max_history_entries:
            self.status_history.pop(0)
        
        # Log da mudança
        self.logger.log_system_event(
            "component_status_change",
            f"{self.component_name}: {old_status.value} -> {new_status.value}",
            {
                "component": self.component_name,
                "old_status": old_status.value,
                "new_status": new_status.value,
                "error_count": self.metrics.error_count,
                "warning_count": self.metrics.warning_count
            },
            level="WARNING" if new_status in [ComponentStatus.WARNING, ComponentStatus.CRITICAL] else "INFO"
        )
        
        # Chamar callbacks
        for callback in self.status_change_callbacks:
            try:
                callback(self.component_name, old_status, new_status, self.metrics)
            except Exception as e:
                self.logger.log_error("status_change_callback", e, {
                    "component": self.component_name
                })
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Retorna resumo da saúde do componente"""
        return {
            "component": self.component_name,
            "status": self.metrics.status.value,
            "uptime_seconds": self.metrics.uptime_seconds,
            "last_check": self.metrics.last_check.isoformat(),
            "error_count": self.metrics.error_count,
            "warning_count": self.metrics.warning_count,
            "last_error": self.metrics.last_error,
            "last_error_time": self.metrics.last_error_time.isoformat() if self.metrics.last_error_time else None,
            "custom_metrics": self.metrics.custom_metrics
        }

class ResilienceManager:
    """
    Gerenciador principal de resiliência do sistema.
    """
    
    def __init__(self, config, logger, capture_manager, buffer_manager):
        """
        Inicializa o gerenciador de resiliência
        
        Args:
            config: Configurações do sistema
            logger: Logger para eventos
            capture_manager: Gerenciador de capturas
            buffer_manager: Gerenciador de buffers
        """
        self.config = config
        self.logger = logger
        self.capture_manager = capture_manager
        self.buffer_manager = buffer_manager
        
        # Monitores de componentes
        self.monitors: Dict[str, ComponentMonitor] = {}
        
        # Estado geral do sistema
        self.system_start_time = datetime.utcnow()
        self.recovery_actions_taken = 0
        
        # Configurar monitores
        self._setup_monitors()
    
    def _setup_monitors(self):
        """Configura os monitores para todos os componentes"""
        
        # Monitor de sistema geral
        system_monitor = ComponentMonitor(
            "system",
            check_interval=30,  # 30 segundos
            health_check_func=self._check_system_health,
            logger=self.logger
        )
        system_monitor.add_status_change_callback(self._on_system_status_change)
        self.monitors["system"] = system_monitor
        
        # Monitores para cada câmera
        for camera_info in self.config.get_all_cameras_info():
            camera_id = camera_info["name"]
            
            camera_monitor = ComponentMonitor(
                camera_id,
                check_interval=10,  # 10 segundos
                health_check_func=lambda cid=camera_id: self._check_camera_health(cid),
                logger=self.logger
            )
            camera_monitor.add_status_change_callback(self._on_camera_status_change)
            self.monitors[camera_id] = camera_monitor
        
        # Monitor de buffer
        buffer_monitor = ComponentMonitor(
            "buffer",
            check_interval=15,  # 15 segundos
            health_check_func=self._check_buffer_health,
            logger=self.logger
        )
        buffer_monitor.add_status_change_callback(self._on_buffer_status_change)
        self.monitors["buffer"] = buffer_monitor
    
    def _check_system_health(self) -> Dict[str, Any]:
        """Verifica a saúde geral do sistema"""
        try:
            metrics = {}
            status = ComponentStatus.HEALTHY
            
            # Verificar uso de CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            metrics["cpu_percent"] = cpu_percent
            
            if cpu_percent > 90:
                status = ComponentStatus.CRITICAL
            elif cpu_percent > 70:
                status = ComponentStatus.WARNING
            
            # Verificar uso de memória
            memory = psutil.virtual_memory()
            metrics["memory_percent"] = memory.percent
            metrics["memory_available_gb"] = memory.available / (1024**3)
            
            if memory.percent > 95:
                status = ComponentStatus.CRITICAL
            elif memory.percent > 85:
                status = ComponentStatus.WARNING
            
            # Verificar espaço em disco
            if self.config.clips_dir.exists():
                disk_usage = psutil.disk_usage(str(self.config.clips_dir))
                disk_percent = (disk_usage.used / disk_usage.total) * 100
                metrics["disk_percent"] = disk_percent
                metrics["disk_free_gb"] = disk_usage.free / (1024**3)
                
                if disk_percent > 95:
                    status = ComponentStatus.CRITICAL
                elif disk_percent > 85:
                    status = ComponentStatus.WARNING
            
            # Verificar temperatura (Linux apenas)
            if platform.system() == "Linux":
                try:
                    temps = psutil.sensors_temperatures()
                    if temps:
                        for name, entries in temps.items():
                            for entry in entries:
                                if entry.current:
                                    metrics[f"temp_{name}"] = entry.current
                                    
                                    if entry.current > 80:
                                        status = ComponentStatus.CRITICAL
                                    elif entry.current > 70:
                                        status = ComponentStatus.WARNING
                except:
                    pass  # Sensores podem não estar disponíveis
            
            return {
                "status": status,
                "metrics": metrics
            }
            
        except Exception as e:
            return {
                "status": ComponentStatus.FAILED,
                "error": str(e)
            }
    
    def _check_camera_health(self, camera_id: str) -> Dict[str, Any]:
        """Verifica a saúde de uma câmera específica"""
        try:
            capture = self.capture_manager.get_capture(camera_id)
            if not capture:
                return {
                    "status": ComponentStatus.FAILED,
                    "error": "Captura não encontrada"
                }
            
            capture_info = capture.get_capture_info()
            metrics = {}
            status = ComponentStatus.HEALTHY
            
            # Verificar se está rodando
            if not capture_info["is_running"]:
                status = ComponentStatus.FAILED
                return {
                    "status": status,
                    "error": "Captura não está rodando",
                    "metrics": metrics
                }
            
            # Verificar idade do último segmento
            last_segment_age = capture_info.get("last_segment_age_seconds")
            if last_segment_age is not None:
                metrics["last_segment_age_seconds"] = last_segment_age
                
                # Se não há segmento há mais de 30 segundos, problema
                if last_segment_age > 30:
                    status = ComponentStatus.WARNING
                if last_segment_age > 60:
                    status = ComponentStatus.CRITICAL
                if last_segment_age > 120:
                    status = ComponentStatus.FAILED
            
            # Verificar tentativas de reconexão
            reconnect_attempts = capture_info.get("reconnect_attempts", 0)
            metrics["reconnect_attempts"] = reconnect_attempts
            
            if reconnect_attempts > 5:
                status = ComponentStatus.WARNING
            if reconnect_attempts > 10:
                status = ComponentStatus.CRITICAL
            
            # Verificar total de segmentos capturados
            total_segments = capture_info.get("total_segments_captured", 0)
            metrics["total_segments_captured"] = total_segments
            
            return {
                "status": status,
                "metrics": metrics
            }
            
        except Exception as e:
            return {
                "status": ComponentStatus.FAILED,
                "error": str(e)
            }
    
    def _check_buffer_health(self) -> Dict[str, Any]:
        """Verifica a saúde dos buffers"""
        try:
            buffers_info = self.buffer_manager.get_all_buffers_info()
            metrics = {}
            status = ComponentStatus.HEALTHY
            
            total_segments = 0
            total_size_bytes = 0
            
            for camera_id, buffer_info in buffers_info.items():
                segments_count = buffer_info["segments_count"]
                size_bytes = buffer_info["total_size_bytes"]
                buffer_usage = buffer_info["buffer_usage_percent"]
                
                total_segments += segments_count
                total_size_bytes += size_bytes
                
                metrics[f"{camera_id}_segments"] = segments_count
                metrics[f"{camera_id}_size_mb"] = size_bytes / (1024**2)
                metrics[f"{camera_id}_usage_percent"] = buffer_usage
                
                # Verificar se buffer está muito vazio
                if buffer_usage < 20:
                    status = ComponentStatus.WARNING
            
            metrics["total_segments"] = total_segments
            metrics["total_size_mb"] = total_size_bytes / (1024**2)
            
            # Verificar espaço disponível no tmpfs/RAM
            if self.config.temp_dir.exists():
                try:
                    disk_usage = psutil.disk_usage(str(self.config.temp_dir))
                    used_percent = (disk_usage.used / disk_usage.total) * 100
                    metrics["temp_dir_usage_percent"] = used_percent
                    
                    if used_percent > 90:
                        status = ComponentStatus.CRITICAL
                    elif used_percent > 75:
                        status = ComponentStatus.WARNING
                except:
                    pass
            
            return {
                "status": status,
                "metrics": metrics
            }
            
        except Exception as e:
            return {
                "status": ComponentStatus.FAILED,
                "error": str(e)
            }
    
    def _on_system_status_change(self, component: str, old_status: ComponentStatus, 
                                new_status: ComponentStatus, metrics: HealthMetrics):
        """Callback para mudanças de status do sistema"""
        if new_status == ComponentStatus.CRITICAL:
            # Sistema crítico - tomar ações drásticas
            self.logger.log_system_event(
                "system_critical",
                "Sistema em estado crítico - executando ações de emergência",
                level="CRITICAL"
            )
            
            # Limpar buffers se necessário para liberar memória
            if metrics.custom_metrics.get("memory_percent", 0) > 95:
                self._emergency_buffer_cleanup()
    
    def _on_camera_status_change(self, component: str, old_status: ComponentStatus,
                                new_status: ComponentStatus, metrics: HealthMetrics):
        """Callback para mudanças de status de câmera"""
        if new_status in [ComponentStatus.FAILED, ComponentStatus.CRITICAL]:
            # Tentar recuperar câmera
            self._attempt_camera_recovery(component)
    
    def _on_buffer_status_change(self, component: str, old_status: ComponentStatus,
                                new_status: ComponentStatus, metrics: HealthMetrics):
        """Callback para mudanças de status do buffer"""
        if new_status == ComponentStatus.CRITICAL:
            # Buffer crítico - limpar buffers antigos
            self._emergency_buffer_cleanup()
    
    def _attempt_camera_recovery(self, camera_id: str):
        """Tenta recuperar uma câmera com problemas"""
        try:
            self.logger.log_system_event(
                "camera_recovery_attempt",
                f"Tentando recuperar câmera {camera_id}",
                {"camera_id": camera_id}
            )
            
            # Reiniciar captura
            success = self.capture_manager.restart_capture(camera_id)
            
            if success:
                self.recovery_actions_taken += 1
                self.logger.log_system_event(
                    "camera_recovery_success",
                    f"Câmera {camera_id} recuperada com sucesso",
                    {"camera_id": camera_id}
                )
            else:
                self.logger.log_system_event(
                    "camera_recovery_failed",
                    f"Falha ao recuperar câmera {camera_id}",
                    {"camera_id": camera_id},
                    level="ERROR"
                )
                
        except Exception as e:
            self.logger.log_error("camera_recovery", e, {
                "camera_id": camera_id
            })
    
    def _emergency_buffer_cleanup(self):
        """Executa limpeza de emergência dos buffers"""
        try:
            self.logger.log_system_event(
                "emergency_buffer_cleanup",
                "Executando limpeza de emergência dos buffers",
                level="WARNING"
            )
            
            # Limpar metade dos buffers de cada câmera
            for camera_id in self.buffer_manager.buffers:
                buffer = self.buffer_manager.get_camera_buffer(camera_id)
                if buffer:
                    # Remover metade dos segmentos mais antigos
                    segments_to_remove = len(buffer.segments) // 2
                    for _ in range(segments_to_remove):
                        if buffer.segments:
                            old_segment = buffer.segments.pop(0)
                            try:
                                if old_segment.filepath.exists():
                                    old_segment.filepath.unlink()
                            except:
                                pass
            
            self.recovery_actions_taken += 1
            
        except Exception as e:
            self.logger.log_error("emergency_cleanup", e)
    
    def start_monitoring(self):
        """Inicia o monitoramento de todos os componentes"""
        for monitor in self.monitors.values():
            monitor.start_monitoring()
        
        self.logger.log_system_event(
            "resilience_monitoring_started",
            f"Monitoramento iniciado para {len(self.monitors)} componentes",
            {"components": list(self.monitors.keys())}
        )
    
    def stop_monitoring(self):
        """Para o monitoramento de todos os componentes"""
        for monitor in self.monitors.values():
            monitor.stop_monitoring()
        
        self.logger.log_system_event(
            "resilience_monitoring_stopped",
            "Monitoramento de resiliência parado"
        )
    
    def get_system_health_summary(self) -> Dict[str, Any]:
        """Retorna resumo completo da saúde do sistema"""
        components_health = {}
        overall_status = ComponentStatus.HEALTHY
        
        for name, monitor in self.monitors.items():
            health = monitor.get_health_summary()
            components_health[name] = health
            
            # Determinar status geral
            component_status = ComponentStatus(health["status"])
            if component_status == ComponentStatus.FAILED:
                overall_status = ComponentStatus.FAILED
            elif component_status == ComponentStatus.CRITICAL and overall_status != ComponentStatus.FAILED:
                overall_status = ComponentStatus.CRITICAL
            elif component_status == ComponentStatus.WARNING and overall_status == ComponentStatus.HEALTHY:
                overall_status = ComponentStatus.WARNING
        
        uptime = (datetime.utcnow() - self.system_start_time).total_seconds()
        
        return {
            "overall_status": overall_status.value,
            "system_uptime_seconds": uptime,
            "recovery_actions_taken": self.recovery_actions_taken,
            "components": components_health,
            "summary": {
                "healthy_components": sum(1 for h in components_health.values() if h["status"] == "healthy"),
                "warning_components": sum(1 for h in components_health.values() if h["status"] == "warning"),
                "critical_components": sum(1 for h in components_health.values() if h["status"] == "critical"),
                "failed_components": sum(1 for h in components_health.values() if h["status"] == "failed"),
                "total_components": len(components_health)
            }
        }
    
    def force_recovery_all(self):
        """Força recuperação de todos os componentes com problemas"""
        health_summary = self.get_system_health_summary()
        
        for component_name, health in health_summary["components"].items():
            status = ComponentStatus(health["status"])
            
            if status in [ComponentStatus.FAILED, ComponentStatus.CRITICAL]:
                if component_name.startswith("camera_"):
                    self._attempt_camera_recovery(component_name)
                elif component_name == "buffer":
                    self._emergency_buffer_cleanup()
        
        self.logger.log_system_event(
            "forced_recovery_completed",
            "Recuperação forçada executada para todos os componentes"
        )
