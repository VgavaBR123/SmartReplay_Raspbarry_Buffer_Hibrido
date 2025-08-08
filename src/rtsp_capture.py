"""
Módulo de captura RTSP com FFmpeg e segmentação automática.
Gerencia processos FFmpeg para captura contínua de vídeo com segmentos de duração fixa.
"""

import os
import subprocess
import threading
import time
import signal
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, Any
import platform

class RTSPCapture:
    """
    Gerencia a captura de uma câmera RTSP usando FFmpeg com segmentação automática.
    """
    
    def __init__(self, camera_id: str, rtsp_url: str, temp_dir: Path, 
                 config, logger, segment_callback: Optional[Callable] = None):
        """
        Inicializa a captura RTSP
        
        Args:
            camera_id: ID da câmera
            rtsp_url: URL RTSP da câmera
            temp_dir: Diretório temporário para segmentos
            config: Configurações do sistema
            logger: Logger para eventos
            segment_callback: Callback chamado quando um novo segmento é criado
        """
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.temp_dir = temp_dir
        self.config = config
        self.logger = logger
        self.segment_callback = segment_callback
        
        # Estado da captura
        self.is_running = False
        self.process: Optional[subprocess.Popen] = None
        self.capture_thread: Optional[threading.Thread] = None
        
        # Controle de reconexão
        self.reconnect_attempts = 0
        self.last_reconnect_time = 0
        
        # Estatísticas
        self.total_segments_captured = 0
        self.start_time: Optional[datetime] = None
        self.last_segment_time: Optional[datetime] = None
        
        # Criar diretório temporário
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def _build_ffmpeg_command(self) -> list:
        """
        Constrói o comando FFmpeg para captura e segmentação
        
        Returns:
            Lista com argumentos do comando FFmpeg
        """
        # Padrão de nome dos arquivos de segmento
        segment_filename = str(self.temp_dir / f"{self.camera_id}_%Y%m%d_%H%M%S.mp4")
        
        cmd = [
            "ffmpeg",
            "-y",  # Sobrescrever arquivos
            "-loglevel", "warning",  # Reduzir verbosidade
            
            # Opções de entrada RTSP
            "-rtsp_transport", self.config.rtsp_transport,
            "-i", self.rtsp_url,
            
            # Configurações de vídeo
            "-c:v", "libx264",  # Codec de vídeo
            "-preset", self.config.ffmpeg_preset,  # Preset de codificação
            "-crf", str(self.config.ffmpeg_crf),  # Qualidade
            
            # Configurações de keyframes (importantes para cortes precisos)
            "-g", str(self.config.ffmpeg_keyframe_interval * 30),  # GOP size (assumindo 30fps)
            "-keyint_min", str(self.config.ffmpeg_keyframe_interval * 30),
            "-force_key_frames", f"expr:gte(t,n_forced*{self.config.ffmpeg_keyframe_interval})",
            
            # Configurações de áudio (copiar se disponível)
            "-c:a", "aac",
            "-b:a", "128k",
            
            # Configurações de segmentação
            "-f", "segment",
            "-segment_time", str(self.config.chunk_duration),
            "-segment_format", "mp4",
            "-segment_atclocktime", "1",  # Alinhar com o relógio
            "-strftime", "1",  # Usar strftime no nome dos arquivos
            
            # Arquivo de saída
            segment_filename
        ]
        
        return cmd
    
    def _monitor_segments(self):
        """
        Monitora a criação de novos segmentos no diretório temporário
        """
        known_segments = set()
        
        while self.is_running:
            try:
                # Verificar novos arquivos no diretório
                current_files = set()
                for file_path in self.temp_dir.glob(f"{self.camera_id}_*.mp4"):
                    if file_path.is_file():
                        current_files.add(file_path.name)
                
                # Identificar novos segmentos
                new_segments = current_files - known_segments
                
                for segment_name in new_segments:
                    segment_path = self.temp_dir / segment_name
                    
                    # Aguardar um pouco para garantir que o arquivo foi completamente escrito
                    time.sleep(0.5)
                    
                    if segment_path.exists():
                        try:
                            size_bytes = segment_path.stat().st_size
                            
                            # Verificar se o arquivo tem tamanho válido
                            if size_bytes > 1000:  # Pelo menos 1KB
                                self.total_segments_captured += 1
                                self.last_segment_time = datetime.utcnow()
                                
                                # Log do evento
                                self.logger.log_camera_event(
                                    self.camera_id, "segment_captured", 
                                    f"Novo segmento: {segment_name}",
                                    {
                                        "filename": segment_name,
                                        "size_bytes": size_bytes,
                                        "total_segments": self.total_segments_captured
                                    }
                                )
                                
                                # Chamar callback se definido
                                if self.segment_callback:
                                    try:
                                        self.segment_callback(self.camera_id, segment_name, size_bytes)
                                    except Exception as e:
                                        self.logger.log_error("segment_callback", e, {
                                            "camera_id": self.camera_id,
                                            "filename": segment_name
                                        })
                            
                        except Exception as e:
                            self.logger.log_error("segment_monitor", e, {
                                "camera_id": self.camera_id,
                                "filename": segment_name
                            })
                
                known_segments = current_files
                time.sleep(1)  # Verificar a cada segundo
                
            except Exception as e:
                if self.is_running:  # Só log se ainda estiver rodando
                    self.logger.log_error("segment_monitor", e, {
                        "camera_id": self.camera_id
                    })
                time.sleep(5)
    
    def start_capture(self) -> bool:
        """
        Inicia a captura de vídeo
        
        Returns:
            True se a captura foi iniciada com sucesso
        """
        if self.is_running:
            self.logger.log_camera_event(
                self.camera_id, "capture_already_running",
                "Captura já está em execução",
                level="WARNING"
            )
            return True
        
        try:
            # Construir comando FFmpeg
            cmd = self._build_ffmpeg_command()
            
            self.logger.log_camera_event(
                self.camera_id, "capture_starting",
                f"Iniciando captura: {' '.join(cmd[:8])}..."  # Log apenas início do comando
            )
            
            # Iniciar processo FFmpeg
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                preexec_fn=None if platform.system() == "Windows" else os.setsid
            )
            
            self.is_running = True
            self.start_time = datetime.utcnow()
            self.reconnect_attempts = 0
            
            # Iniciar thread de monitoramento de segmentos
            monitor_thread = threading.Thread(
                target=self._monitor_segments,
                name=f"SegmentMonitor-{self.camera_id}",
                daemon=True
            )
            monitor_thread.start()
            
            # Iniciar thread de captura
            self.capture_thread = threading.Thread(
                target=self._capture_worker,
                name=f"CaptureWorker-{self.camera_id}",
                daemon=True
            )
            self.capture_thread.start()
            
            self.logger.log_camera_event(
                self.camera_id, "capture_started",
                f"Captura iniciada com PID {self.process.pid}"
            )
            
            return True
            
        except Exception as e:
            self.logger.log_error("capture_start", e, {
                "camera_id": self.camera_id,
                "rtsp_url": self.rtsp_url
            })
            self.is_running = False
            return False
    
    def _capture_worker(self):
        """Worker thread que monitora o processo FFmpeg"""
        while self.is_running and self.process:
            try:
                # Verificar se o processo ainda está rodando
                return_code = self.process.poll()
                
                if return_code is not None:
                    # Processo terminou
                    stdout, stderr = self.process.communicate(timeout=5)
                    
                    self.logger.log_camera_event(
                        self.camera_id, "capture_ended",
                        f"FFmpeg terminou com código {return_code}",
                        {
                            "return_code": return_code,
                            "stderr": stderr.decode('utf-8', errors='ignore')[-500:] if stderr else None
                        },
                        level="ERROR" if return_code != 0 else "INFO"
                    )
                    
                    if self.is_running:  # Se ainda deveria estar rodando, tentar reconectar
                        self._schedule_reconnect()
                    
                    break
                
                time.sleep(2)  # Verificar a cada 2 segundos
                
            except Exception as e:
                self.logger.log_error("capture_worker", e, {
                    "camera_id": self.camera_id
                })
                if self.is_running:
                    self._schedule_reconnect()
                break
    
    def _schedule_reconnect(self):
        """Agenda uma tentativa de reconexão"""
        if not self.is_running:
            return
        
        self.reconnect_attempts += 1
        
        # Calcular delay com backoff exponencial
        delay = min(
            self.config.reconnect_initial_delay * (2 ** (self.reconnect_attempts - 1)),
            self.config.reconnect_max_delay
        )
        
        # Verificar se excedeu máximo de tentativas
        if (self.config.reconnect_max_attempts > 0 and 
            self.reconnect_attempts > self.config.reconnect_max_attempts):
            
            self.logger.log_camera_event(
                self.camera_id, "max_reconnects_exceeded",
                f"Máximo de {self.config.reconnect_max_attempts} tentativas excedido",
                level="ERROR"
            )
            self.stop_capture()
            return
        
        self.logger.log_reconnection_event(
            self.camera_id, self.reconnect_attempts,
            self.config.reconnect_max_attempts, delay
        )
        
        # Aguardar e tentar reconectar
        def reconnect_worker():
            time.sleep(delay)
            if self.is_running:
                self._cleanup_process()
                self.start_capture()
        
        threading.Thread(target=reconnect_worker, daemon=True).start()
    
    def stop_capture(self):
        """Para a captura de vídeo"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        self.logger.log_camera_event(
            self.camera_id, "capture_stopping",
            "Parando captura de vídeo"
        )
        
        self._cleanup_process()
        
        # Aguardar thread de captura terminar
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=5)
        
        self.logger.log_camera_event(
            self.camera_id, "capture_stopped",
            f"Captura parada. Total de segmentos: {self.total_segments_captured}"
        )
    
    def _cleanup_process(self):
        """Limpa o processo FFmpeg"""
        if self.process:
            try:
                if platform.system() == "Windows":
                    # No Windows, terminar o processo
                    self.process.terminate()
                else:
                    # No Linux, matar o grupo de processos
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                
                # Aguardar um pouco e forçar se necessário
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if platform.system() == "Windows":
                        self.process.kill()
                    else:
                        os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    self.process.wait()
                
            except Exception as e:
                self.logger.log_error("process_cleanup", e, {
                    "camera_id": self.camera_id,
                    "pid": self.process.pid if self.process else None
                })
            
            finally:
                self.process = None
    
    def get_capture_info(self) -> Dict[str, Any]:
        """
        Retorna informações sobre o estado da captura
        
        Returns:
            Dicionário com informações da captura
        """
        uptime = None
        if self.start_time:
            uptime = (datetime.utcnow() - self.start_time).total_seconds()
        
        last_segment_age = None
        if self.last_segment_time:
            last_segment_age = (datetime.utcnow() - self.last_segment_time).total_seconds()
        
        return {
            "camera_id": self.camera_id,
            "rtsp_url": self.rtsp_url,
            "is_running": self.is_running,
            "process_pid": self.process.pid if self.process else None,
            "uptime_seconds": uptime,
            "total_segments_captured": self.total_segments_captured,
            "last_segment_time": self.last_segment_time.isoformat() if self.last_segment_time else None,
            "last_segment_age_seconds": last_segment_age,
            "reconnect_attempts": self.reconnect_attempts,
            "temp_dir": str(self.temp_dir)
        }
    
    def restart_capture(self) -> bool:
        """
        Reinicia a captura
        
        Returns:
            True se reiniciado com sucesso
        """
        self.logger.log_camera_event(
            self.camera_id, "capture_restarting",
            "Reiniciando captura"
        )
        
        self.stop_capture()
        time.sleep(2)  # Aguardar um pouco antes de reiniciar
        return self.start_capture()

class RTSPCaptureManager:
    """
    Gerenciador de múltiplas capturas RTSP.
    """
    
    def __init__(self, config, logger, buffer_manager):
        """
        Inicializa o gerenciador de capturas
        
        Args:
            config: Configurações do sistema
            logger: Logger para eventos
            buffer_manager: Gerenciador de buffers
        """
        self.config = config
        self.logger = logger
        self.buffer_manager = buffer_manager
        self.captures: Dict[str, RTSPCapture] = {}
        
        # Criar capturas para cada câmera
        for camera_info in config.get_all_cameras_info():
            camera_id = camera_info["name"]
            capture = RTSPCapture(
                camera_id=camera_id,
                rtsp_url=camera_info["url"],
                temp_dir=camera_info["temp_dir"],
                config=config,
                logger=logger,
                segment_callback=self._on_segment_created
            )
            self.captures[camera_id] = capture
        
        self.logger.log_system_event(
            "capture_manager_initialized",
            f"Capturas criadas para {len(self.captures)} câmeras",
            {"cameras": list(self.captures.keys())}
        )
    
    def _on_segment_created(self, camera_id: str, filename: str, size_bytes: int):
        """
        Callback chamado quando um novo segmento é criado
        
        Args:
            camera_id: ID da câmera
            filename: Nome do arquivo
            size_bytes: Tamanho em bytes
        """
        # Adicionar segmento ao buffer
        self.buffer_manager.add_segment(camera_id, filename, size_bytes)
    
    def start_all_captures(self) -> bool:
        """
        Inicia todas as capturas
        
        Returns:
            True se todas foram iniciadas com sucesso
        """
        success = True
        
        for camera_id, capture in self.captures.items():
            if not capture.start_capture():
                success = False
        
        if success:
            self.logger.log_system_event(
                "all_captures_started",
                f"Todas as {len(self.captures)} capturas foram iniciadas"
            )
        else:
            self.logger.log_system_event(
                "captures_start_partial_failure",
                "Algumas capturas falharam ao iniciar",
                level="WARNING"
            )
        
        return success
    
    def stop_all_captures(self):
        """Para todas as capturas"""
        for capture in self.captures.values():
            capture.stop_capture()
        
        self.logger.log_system_event(
            "all_captures_stopped",
            "Todas as capturas foram paradas"
        )
    
    def get_all_captures_info(self) -> Dict[str, Dict]:
        """
        Retorna informações de todas as capturas
        
        Returns:
            Dicionário com informações de cada captura
        """
        return {
            camera_id: capture.get_capture_info()
            for camera_id, capture in self.captures.items()
        }
    
    def restart_capture(self, camera_id: str) -> bool:
        """
        Reinicia uma captura específica
        
        Args:
            camera_id: ID da câmera
            
        Returns:
            True se reiniciado com sucesso
        """
        if camera_id not in self.captures:
            return False
        
        return self.captures[camera_id].restart_capture()
    
    def get_capture(self, camera_id: str) -> Optional[RTSPCapture]:
        """
        Retorna uma captura específica
        
        Args:
            camera_id: ID da câmera
            
        Returns:
            Instância da captura ou None se não encontrada
        """
        return self.captures.get(camera_id)
