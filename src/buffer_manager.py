"""
Gerenciador de buffer circular para armazenamento de segmentos de vídeo em RAM/tmpfs.
Mantém apenas os últimos N segundos de vídeo por câmera, removendo automaticamente
arquivos antigos quando novos segmentos são criados.
"""

import os
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import threading

@dataclass
class BufferSegment:
    """Representa um segmento no buffer"""
    filename: str
    filepath: Path
    timestamp: datetime
    duration: float
    size_bytes: int
    
    @property
    def age_seconds(self) -> float:
        """Idade do segmento em segundos"""
        return (datetime.utcnow() - self.timestamp).total_seconds()

class CircularBuffer:
    """
    Buffer circular para uma câmera específica.
    Mantém apenas os últimos N segundos de vídeo.
    """
    
    def __init__(self, camera_id: str, temp_dir: Path, max_duration: float, 
                 chunk_duration: float, logger):
        """
        Inicializa o buffer circular
        
        Args:
            camera_id: ID da câmera
            temp_dir: Diretório temporário para armazenar segmentos
            max_duration: Duração máxima do buffer em segundos
            chunk_duration: Duração de cada chunk em segundos
            logger: Logger para eventos
        """
        self.camera_id = camera_id
        self.temp_dir = temp_dir
        self.max_duration = max_duration
        self.chunk_duration = chunk_duration
        self.logger = logger
        
        # Lista de segmentos ordenada por timestamp (mais antigo primeiro)
        self.segments: List[BufferSegment] = []
        self.lock = threading.RLock()
        
        # Proteção contra condição de corrida durante geração de clipes
        self.clip_generation_active = False
        self.frozen_segments: List[BufferSegment] = []
        
        # Estatísticas
        self.total_segments_created = 0
        self.total_segments_removed = 0
        self.total_bytes_processed = 0
        
        # Criar diretório se não existir
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Carregar segmentos existentes (recovery)
        self._load_existing_segments()
    
    def _load_existing_segments(self):
        """Carrega segmentos existentes no diretório (para recovery)"""
        try:
            pattern = f"{self.camera_id}_*.mp4"
            existing_files = list(self.temp_dir.glob(pattern))
            
            for filepath in existing_files:
                try:
                    stat = filepath.stat()
                    # Extrair timestamp do nome do arquivo se possível
                    timestamp = datetime.fromtimestamp(stat.st_mtime)
                    
                    segment = BufferSegment(
                        filename=filepath.name,
                        filepath=filepath,
                        timestamp=timestamp,
                        duration=self.chunk_duration,
                        size_bytes=stat.st_size
                    )
                    
                    self.segments.append(segment)
                    
                except Exception as e:
                    self.logger.log_error("buffer", e, {
                        "camera_id": self.camera_id,
                        "file": str(filepath)
                    })
            
            # Ordenar por timestamp
            self.segments.sort(key=lambda s: s.timestamp)
            
            # Remover segmentos antigos se necessário
            self._cleanup_old_segments()
            
            if self.segments:
                self.logger.log_buffer_event(
                    self.camera_id, "recovery_completed", 
                    f"loaded_{len(self.segments)}_segments",
                    {"segments_count": len(self.segments)}
                )
                
        except Exception as e:
            self.logger.log_error("buffer", e, {"camera_id": self.camera_id})
    
    def add_segment(self, filename: str, size_bytes: int) -> bool:
        """
        Adiciona um novo segmento ao buffer
        
        Args:
            filename: Nome do arquivo do segmento
            size_bytes: Tamanho do arquivo em bytes
            
        Returns:
            True se o segmento foi adicionado com sucesso
        """
        with self.lock:
            try:
                filepath = self.temp_dir / filename
                
                # Verificar se o arquivo existe
                if not filepath.exists():
                    self.logger.log_camera_event(
                        self.camera_id, "segment_not_found", 
                        f"Arquivo não encontrado: {filename}",
                        level="WARNING"
                    )
                    return False
                
                # Criar segmento
                segment = BufferSegment(
                    filename=filename,
                    filepath=filepath,
                    timestamp=datetime.utcnow(),
                    duration=self.chunk_duration,
                    size_bytes=size_bytes
                )
                
                # Adicionar à lista
                self.segments.append(segment)
                self.total_segments_created += 1
                self.total_bytes_processed += size_bytes
                
                # Log do evento
                self.logger.log_buffer_event(
                    self.camera_id, "segment_created", filename,
                    {
                        "size_bytes": size_bytes,
                        "buffer_size": len(self.segments),
                        "total_duration": len(self.segments) * self.chunk_duration
                    }
                )
                
                # Remover segmentos antigos se necessário
                self._cleanup_old_segments()
                
                return True
                
            except Exception as e:
                self.logger.log_error("buffer", e, {
                    "camera_id": self.camera_id,
                    "filename": filename
                })
                return False
    
    def _cleanup_old_segments(self):
        """Remove segmentos antigos que excedem a duração máxima do buffer"""
        # CORREÇÃO: Não limpar durante geração de clipes
        if self.clip_generation_active:
            return
            
        while self.segments:
            total_duration = len(self.segments) * self.chunk_duration
            
            if total_duration <= self.max_duration:
                break
            
            # Remover o segmento mais antigo
            old_segment = self.segments.pop(0)
            
            try:
                # Remover arquivo do disco
                if old_segment.filepath.exists():
                    old_segment.filepath.unlink()
                
                self.total_segments_removed += 1
                
                # Log do evento
                self.logger.log_buffer_event(
                    self.camera_id, "segment_removed", old_segment.filename,
                    {
                        "age_seconds": old_segment.age_seconds,
                        "size_bytes": old_segment.size_bytes,
                        "buffer_size": len(self.segments)
                    }
                )
                
            except Exception as e:
                self.logger.log_error("buffer", e, {
                    "camera_id": self.camera_id,
                    "filename": old_segment.filename
                })
    
    def get_recent_segments(self, duration: float) -> List[BufferSegment]:
        """
        Retorna segmentos dos últimos N segundos
        
        Args:
            duration: Duração em segundos
            
        Returns:
            Lista de segmentos ordenada por timestamp (mais antigo primeiro)
        """
        with self.lock:
            if not self.segments:
                return []
            
            # Calcular quantos chunks precisamos
            chunks_needed = max(1, int(duration / self.chunk_duration))
            
            # CORREÇÃO: Usar segmentos congelados se disponíveis
            segments_to_use = self.frozen_segments if self.clip_generation_active else self.segments
            
            # Retornar os últimos N chunks
            return segments_to_use[-chunks_needed:] if len(segments_to_use) >= chunks_needed else segments_to_use
    
    def get_segments_for_timerange(self, start_time: datetime, 
                                  end_time: datetime) -> List[BufferSegment]:
        """
        Retorna segmentos para um intervalo de tempo específico
        
        Args:
            start_time: Tempo de início
            end_time: Tempo de fim
            
        Returns:
            Lista de segmentos no intervalo
        """
        with self.lock:
            result = []
            
            for segment in self.segments:
                # Verificar se o segmento se sobrepõe ao intervalo
                segment_start = segment.timestamp
                segment_end = segment.timestamp + timedelta(seconds=segment.duration)
                
                if (segment_start <= end_time and segment_end >= start_time):
                    result.append(segment)
            
            return result
    
    def get_buffer_info(self) -> Dict:
        """
        Retorna informações sobre o estado atual do buffer
        
        Returns:
            Dicionário com estatísticas do buffer
        """
        with self.lock:
            if self.segments:
                oldest_segment = self.segments[0]
                newest_segment = self.segments[-1]
                total_size = sum(s.size_bytes for s in self.segments)
                total_duration = len(self.segments) * self.chunk_duration
            else:
                oldest_segment = None
                newest_segment = None
                total_size = 0
                total_duration = 0
            
            return {
                "camera_id": self.camera_id,
                "segments_count": len(self.segments),
                "total_duration_seconds": total_duration,
                "total_size_bytes": total_size,
                "max_duration_seconds": self.max_duration,
                "chunk_duration_seconds": self.chunk_duration,
                "oldest_segment": oldest_segment.filename if oldest_segment else None,
                "newest_segment": newest_segment.filename if newest_segment else None,
                "oldest_timestamp": oldest_segment.timestamp.isoformat() if oldest_segment else None,
                "newest_timestamp": newest_segment.timestamp.isoformat() if newest_segment else None,
                "buffer_usage_percent": (total_duration / self.max_duration) * 100,
                "stats": {
                    "total_created": self.total_segments_created,
                    "total_removed": self.total_segments_removed,
                    "total_bytes_processed": self.total_bytes_processed
                }
            }
    
    def clear_buffer(self):
        """Remove todos os segmentos do buffer"""
        with self.lock:
            for segment in self.segments:
                try:
                    if segment.filepath.exists():
                        segment.filepath.unlink()
                except Exception as e:
                    self.logger.log_error("buffer", e, {
                        "camera_id": self.camera_id,
                        "filename": segment.filename
                    })
            
            self.segments.clear()
            
            self.logger.log_buffer_event(
                self.camera_id, "buffer_cleared", "all_segments_removed"
            )
    
    def freeze_for_clip_generation(self):
        """
        Congela o buffer para geração de clipe, evitando limpeza durante o processo
        """
        with self.lock:
            self.clip_generation_active = True
            self.frozen_segments = self.segments.copy()
            
            self.logger.log_buffer_event(
                self.camera_id, "buffer_frozen", f"froze_{len(self.frozen_segments)}_segments",
                {"frozen_segments_count": len(self.frozen_segments)}
            )
    
    def unfreeze_after_clip_generation(self):
        """
        Descongela o buffer após geração de clipe
        """
        with self.lock:
            self.clip_generation_active = False
            self.frozen_segments.clear()
            
            # Executar limpeza postergada se necessário
            self._cleanup_old_segments()
            
            self.logger.log_buffer_event(
                self.camera_id, "buffer_unfrozen", "buffer_unfrozen"
            )

class BufferManager:
    """
    Gerenciador principal de buffers para todas as câmeras.
    """
    
    def __init__(self, config, logger):
        """
        Inicializa o gerenciador de buffers
        
        Args:
            config: Configurações do sistema
            logger: Logger para eventos
        """
        self.config = config
        self.logger = logger
        self.buffers: Dict[str, CircularBuffer] = {}
        
        # Criar buffers para cada câmera
        for camera_info in config.get_all_cameras_info():
            camera_id = camera_info["name"]
            buffer = CircularBuffer(
                camera_id=camera_id,
                temp_dir=camera_info["temp_dir"],
                max_duration=config.buffer_seconds,
                chunk_duration=config.chunk_duration,
                logger=logger
            )
            self.buffers[camera_id] = buffer
        
        self.logger.log_system_event(
            "buffer_manager_initialized",
            f"Buffers criados para {len(self.buffers)} câmeras",
            {"cameras": list(self.buffers.keys())}
        )
    
    def add_segment(self, camera_id: str, filename: str, size_bytes: int) -> bool:
        """
        Adiciona um segmento ao buffer de uma câmera
        
        Args:
            camera_id: ID da câmera
            filename: Nome do arquivo
            size_bytes: Tamanho em bytes
            
        Returns:
            True se adicionado com sucesso
        """
        if camera_id not in self.buffers:
            self.logger.log_system_event(
                "buffer_error",
                f"Buffer não encontrado para câmera: {camera_id}",
                level="ERROR"
            )
            return False
        
        return self.buffers[camera_id].add_segment(filename, size_bytes)
    
    def get_recent_segments(self, camera_id: str, duration: float) -> List[BufferSegment]:
        """
        Retorna segmentos recentes de uma câmera
        
        Args:
            camera_id: ID da câmera
            duration: Duração em segundos
            
        Returns:
            Lista de segmentos
        """
        if camera_id not in self.buffers:
            return []
        
        return self.buffers[camera_id].get_recent_segments(duration)
    
    def get_all_buffers_info(self) -> Dict[str, Dict]:
        """
        Retorna informações de todos os buffers
        
        Returns:
            Dicionário com informações de cada buffer
        """
        return {
            camera_id: buffer.get_buffer_info()
            for camera_id, buffer in self.buffers.items()
        }
    
    def clear_all_buffers(self):
        """Remove todos os segmentos de todos os buffers"""
        for buffer in self.buffers.values():
            buffer.clear_buffer()
        
        self.logger.log_system_event(
            "all_buffers_cleared",
            "Todos os buffers foram limpos"
        )
    
    def get_camera_buffer(self, camera_id: str) -> Optional[CircularBuffer]:
        """
        Retorna o buffer de uma câmera específica
        
        Args:
            camera_id: ID da câmera
            
        Returns:
            Buffer da câmera ou None se não encontrado
        """
        return self.buffers.get(camera_id)
