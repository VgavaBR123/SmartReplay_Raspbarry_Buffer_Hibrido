"""
Módulo de configuração para o sistema de buffer de vídeo RTSP.
Carrega configurações do arquivo .env e valida parâmetros.
"""

import os
import platform
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv

class Config:
    """Classe para gerenciar configurações do sistema."""
    
    def __init__(self, env_file: str = "config.env"):
        """
        Inicializa as configurações carregando do arquivo .env
        
        Args:
            env_file: Caminho para o arquivo de configuração
        """
        self.env_file = env_file
        self._load_config()
        self._validate_config()
        self._setup_directories()
    
    def _load_config(self):
        """Carrega configurações do arquivo .env"""
        load_dotenv(self.env_file)
        
        # URLs das câmeras
        self.camera_urls = []
        camera_num = 1
        while True:
            url_key = f"CAMERA_{camera_num}_URL"
            if url_key in os.environ:
                self.camera_urls.append(os.getenv(url_key))
                camera_num += 1
            else:
                break
        
        # Parâmetros de segmentação e buffer
        self.chunk_duration = int(os.getenv("CHUNK_DURATION", "5"))
        self.buffer_seconds = int(os.getenv("BUFFER_SECONDS", "30"))
        self.final_clip_duration = int(os.getenv("FINAL_CLIP_DURATION", "25"))
        
        # Configurações de transporte
        self.rtsp_transport = os.getenv("RTSP_TRANSPORT", "tcp")
        
        # Diretórios
        self.temp_dir = self._get_temp_directory()
        self.clips_dir = Path(os.getenv("CLIPS_DIR", "./clips"))
        
        # Configurações de reconexão
        self.reconnect_initial_delay = int(os.getenv("RECONNECT_INITIAL_DELAY", "2"))
        self.reconnect_max_delay = int(os.getenv("RECONNECT_MAX_DELAY", "30"))
        self.reconnect_max_attempts = int(os.getenv("RECONNECT_MAX_ATTEMPTS", "0"))
        
        # Modo de gatilho
        self.trigger_mode = os.getenv("TRIGGER_MODE", "keyboard")
        self.http_port = int(os.getenv("HTTP_PORT", "8080"))
        
        # Configurações de log
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.log_format = os.getenv("LOG_FORMAT", "json")
        
        # Configurações de FFmpeg
        self.ffmpeg_keyframe_interval = int(os.getenv("FFMPEG_KEYFRAME_INTERVAL", "1"))
        self.ffmpeg_preset = os.getenv("FFMPEG_PRESET", "ultrafast")
        self.ffmpeg_crf = int(os.getenv("FFMPEG_CRF", "23"))
        
        # Configurações específicas do Windows
        self.use_windows_ramdisk = os.getenv("USE_WINDOWS_RAMDISK", "false").lower() == "true"
        self.windows_ramdisk_size = int(os.getenv("WINDOWS_RAMDISK_SIZE", "2048"))
    
    def _get_temp_directory(self) -> Path:
        """Determina o diretório temporário baseado no sistema operacional"""
        temp_dir_str = os.getenv("TEMP_DIR")
        
        if temp_dir_str:
            return Path(temp_dir_str)
        
        # Detecção automática baseada no SO
        if platform.system() == "Linux":
            # Verifica se /dev/shm está disponível (tmpfs)
            if Path("/dev/shm").exists():
                return Path("/dev/shm/video_buffer")
            else:
                return Path("/tmp/video_buffer")
        elif platform.system() == "Windows":
            if self.use_windows_ramdisk:
                # Se ramdisk estiver configurado, usar
                return Path("R:/video_buffer")
            else:
                # Usar diretório temporário do sistema
                return Path(os.getenv("TEMP", "C:/temp")) / "video_buffer"
        else:
            # macOS e outros
            return Path("/tmp/video_buffer")
    
    def _validate_config(self):
        """Valida as configurações carregadas"""
        if not self.camera_urls:
            raise ValueError("Nenhuma URL de câmera configurada. Configure pelo menos CAMERA_1_URL.")
        
        if self.chunk_duration <= 0:
            raise ValueError("CHUNK_DURATION deve ser maior que 0")
        
        if self.buffer_seconds <= 0:
            raise ValueError("BUFFER_SECONDS deve ser maior que 0")
        
        if self.final_clip_duration <= 0:
            raise ValueError("FINAL_CLIP_DURATION deve ser maior que 0")
        
        if self.final_clip_duration > self.buffer_seconds:
            raise ValueError("FINAL_CLIP_DURATION não pode ser maior que BUFFER_SECONDS")
        
        if self.trigger_mode not in ["keyboard", "http"]:
            raise ValueError("TRIGGER_MODE deve ser 'keyboard' ou 'http'")
        
        # Validação de URLs RTSP
        for i, url in enumerate(self.camera_urls, 1):
            if not url.startswith("rtsp://"):
                raise ValueError(f"CAMERA_{i}_URL deve começar com 'rtsp://'")
    
    def _setup_directories(self):
        """Cria os diretórios necessários se não existirem"""
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        
        # Criar subdiretórios para cada câmera no buffer temporário
        for i in range(len(self.camera_urls)):
            camera_temp_dir = self.temp_dir / f"camera_{i+1}"
            camera_temp_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def buffer_chunks_count(self) -> int:
        """Número de chunks que cabem no buffer"""
        return self.buffer_seconds // self.chunk_duration
    
    @property
    def final_clip_chunks_count(self) -> int:
        """Número de chunks necessários para o clipe final"""
        return self.final_clip_duration // self.chunk_duration
    
    def get_camera_temp_dir(self, camera_index: int) -> Path:
        """Retorna o diretório temporário para uma câmera específica"""
        return self.temp_dir / f"camera_{camera_index + 1}"
    
    def get_camera_info(self, camera_index: int) -> Dict[str, Any]:
        """Retorna informações de uma câmera específica"""
        if camera_index >= len(self.camera_urls):
            raise IndexError(f"Índice de câmera {camera_index} inválido")
        
        return {
            "index": camera_index,
            "url": self.camera_urls[camera_index],
            "temp_dir": self.get_camera_temp_dir(camera_index),
            "name": f"camera_{camera_index + 1}"
        }
    
    def get_all_cameras_info(self) -> List[Dict[str, Any]]:
        """Retorna informações de todas as câmeras"""
        return [self.get_camera_info(i) for i in range(len(self.camera_urls))]
    
    def __str__(self) -> str:
        """Representação string das configurações"""
        return f"""Configurações do Sistema:
- Câmeras: {len(self.camera_urls)}
- Duração do chunk: {self.chunk_duration}s
- Buffer: {self.buffer_seconds}s ({self.buffer_chunks_count} chunks)
- Clipe final: {self.final_clip_duration}s ({self.final_clip_chunks_count} chunks)
- Diretório temporário: {self.temp_dir}
- Diretório de clipes: {self.clips_dir}
- Modo de gatilho: {self.trigger_mode}
"""
