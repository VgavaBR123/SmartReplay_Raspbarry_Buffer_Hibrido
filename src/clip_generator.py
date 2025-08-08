"""
Gerador de clipes de vídeo com concatenação e cortes precisos.
Suporte para modo rápido (sem reencode) e modo preciso (com reencode parcial).
"""

import os
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict, Any
import math
import shutil

class ClipGenerator:
    """
    Gerador de clipes de vídeo a partir de segmentos armazenados no buffer.
    """
    
    def __init__(self, config, logger, buffer_manager):
        """
        Inicializa o gerador de clipes
        
        Args:
            config: Configurações do sistema
            logger: Logger para eventos
            buffer_manager: Gerenciador de buffers
        """
        self.config = config
        self.logger = logger
        self.buffer_manager = buffer_manager
        
        # Estatísticas
        self.clips_generated = 0
        self.total_processing_time = 0
    
    def generate_clip(self, camera_id: str, trigger_time: datetime, 
                     duration: Optional[float] = None) -> bool:
        """
        Gera um clipe de vídeo para uma câmera específica
        
        Args:
            camera_id: ID da câmera
            trigger_time: Momento do gatilho
            duration: Duração do clipe (usa configuração padrão se None)
            
        Returns:
            True se o clipe foi gerado com sucesso
        """
        start_time = datetime.utcnow()
        
        # Usar duração padrão se não especificada
        if duration is None:
            duration = self.config.final_clip_duration
        
        self.logger.log_camera_event(
            camera_id, "clip_generation_started",
            f"Iniciando geração de clipe de {duration}s",
            {
                "trigger_time": trigger_time.isoformat(),
                "duration": duration
            }
        )
        
        # CORREÇÃO: Congelar buffer durante geração para evitar condição de corrida
        buffer = self.buffer_manager.get_camera_buffer(camera_id)
        if buffer:
            buffer.freeze_for_clip_generation()
        
        try:
            # Obter segmentos necessários do buffer
            segments = self._get_segments_for_clip(camera_id, trigger_time, duration)
            
            if not segments:
                self.logger.log_camera_event(
                    camera_id, "clip_generation_failed",
                    "Nenhum segmento disponível para o clipe",
                    level="ERROR"
                )
                return False
            
            # Verificar se podemos usar modo rápido
            use_fast_mode = self._can_use_fast_mode(trigger_time, duration)
            
            # Gerar nome do arquivo
            clip_filename = self._generate_clip_filename(camera_id, trigger_time)
            clip_path = self.config.clips_dir / clip_filename
            
            # Gerar clipe
            if use_fast_mode:
                success = self._generate_clip_fast(segments, clip_path, duration)
            else:
                success = self._generate_clip_precise(segments, clip_path, trigger_time, duration)
            
            if success:
                # Calcular tempo de processamento
                processing_time = (datetime.utcnow() - start_time).total_seconds()
                self.clips_generated += 1
                self.total_processing_time += processing_time
                
                # Verificar tamanho do arquivo gerado
                file_size = clip_path.stat().st_size if clip_path.exists() else 0
                
                # Log do sucesso
                self.logger.log_clip_event(
                    camera_id, str(clip_filename), trigger_time, duration,
                    [s.filename for s in segments]
                )
                
                self.logger.log_camera_event(
                    camera_id, "clip_generation_completed",
                    f"Clipe gerado: {clip_filename}",
                    {
                        "clip_path": str(clip_path),
                        "file_size_bytes": file_size,
                        "processing_time_seconds": processing_time,
                        "mode": "fast" if use_fast_mode else "precise",
                        "segments_used": len(segments)
                    }
                )
                
                return True
            else:
                self.logger.log_camera_event(
                    camera_id, "clip_generation_failed",
                    "Erro durante a geração do clipe",
                    level="ERROR"
                )
                return False
                
        except Exception as e:
            self.logger.log_error("clip_generation", e, {
                "camera_id": camera_id,
                "trigger_time": trigger_time.isoformat(),
                "duration": duration
            })
            return False
        
        finally:
            # CORREÇÃO: Sempre descongelar buffer
            if buffer:
                buffer.unfreeze_after_clip_generation()
    
    def _get_segments_for_clip(self, camera_id: str, trigger_time: datetime, 
                              duration: float) -> List:
        """
        Obtém os segmentos necessários para gerar o clipe
        
        Args:
            camera_id: ID da câmera
            trigger_time: Momento do gatilho
            duration: Duração do clipe
            
        Returns:
            Lista de segmentos ordenados por timestamp
        """
        # Calcular tempo de início do clipe
        clip_start_time = trigger_time - timedelta(seconds=duration)
        
        # Obter buffer da câmera
        buffer = self.buffer_manager.get_camera_buffer(camera_id)
        if not buffer:
            return []
        
        # Obter segmentos para o intervalo de tempo
        segments = buffer.get_segments_for_timerange(clip_start_time, trigger_time)
        
        # Se não temos segmentos para o intervalo exato, pegar os mais recentes
        if not segments:
            segments = buffer.get_recent_segments(duration)
        
        # Filtrar apenas segmentos que existem no disco
        valid_segments = []
        for segment in segments:
            if segment.filepath.exists():
                valid_segments.append(segment)
            else:
                self.logger.log_camera_event(
                    camera_id, "segment_missing",
                    f"Segmento não encontrado: {segment.filename}",
                    level="WARNING"
                )
        
        # CORREÇÃO: Garantir duração mínima do clipe
        # Se temos menos segmentos que o necessário, tentar obter mais
        minimum_chunks = max(1, int(duration / self.config.chunk_duration))
        if len(valid_segments) < minimum_chunks:
            self.logger.log_camera_event(
                camera_id, "insufficient_segments",
                f"Apenas {len(valid_segments)} segmentos disponíveis para {duration}s de clipe",
                {
                    "available_segments": len(valid_segments),
                    "minimum_required": minimum_chunks,
                    "duration_requested": duration
                },
                level="WARNING"
            )
            
            # Tentar obter todos os segmentos disponíveis
            all_segments = buffer.get_recent_segments(self.config.buffer_seconds)
            valid_segments = []
            for segment in all_segments:
                if segment.filepath.exists():
                    valid_segments.append(segment)
            
            # Se ainda não temos o suficiente, logar erro crítico
            if len(valid_segments) < minimum_chunks:
                self.logger.log_camera_event(
                    camera_id, "critical_insufficient_segments",
                    f"Impossível gerar clipe: apenas {len(valid_segments)} segmentos no buffer",
                    level="ERROR"
                )
        
        return valid_segments
    
    def _can_use_fast_mode(self, trigger_time: datetime, duration: float) -> bool:
        """
        Verifica se pode usar modo rápido (sem reencode)
        
        Args:
            trigger_time: Momento do gatilho
            duration: Duração do clipe
            
        Returns:
            True se pode usar modo rápido
        """
        # Verificar se o trigger time está alinhado com fronteiras de chunk
        seconds_in_minute = trigger_time.second + (trigger_time.microsecond / 1000000)
        
        # Verificar se está próximo de uma fronteira de chunk (múltiplo de chunk_duration)
        chunk_boundary = round(seconds_in_minute / self.config.chunk_duration) * self.config.chunk_duration
        time_diff = abs(seconds_in_minute - chunk_boundary)
        
        # Considerar "próximo" se está dentro de 0.5 segundos da fronteira
        is_near_boundary = time_diff <= 0.5
        
        # Verificar se a duração é múltiplo exato de chunk_duration
        is_duration_aligned = (duration % self.config.chunk_duration) == 0
        
        return is_near_boundary and is_duration_aligned
    
    def _generate_clip_filename(self, camera_id: str, trigger_time: datetime) -> str:
        """
        Gera nome do arquivo do clipe
        
        Args:
            camera_id: ID da câmera
            trigger_time: Momento do gatilho
            
        Returns:
            Nome do arquivo
        """
        timestamp = trigger_time.strftime("%Y%m%d_%H%M%S")
        return f"{camera_id}_clip_{timestamp}Z.mp4"
    
    def _generate_clip_fast(self, segments: List, clip_path: Path, duration: float) -> bool:
        """
        Gera clipe em modo rápido (concatenação sem reencode)
        
        Args:
            segments: Lista de segmentos
            clip_path: Caminho do arquivo de saída
            duration: Duração desejada
            
        Returns:
            True se gerado com sucesso
        """
        try:
            # Calcular quantos segmentos precisamos
            segments_needed = math.ceil(duration / self.config.chunk_duration)
            
            # Usar os últimos N segmentos
            segments_to_use = segments[-segments_needed:] if len(segments) >= segments_needed else segments
            
            if not segments_to_use:
                return False
            
            # Criar arquivo temporário para lista de concatenação
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as concat_file:
                for segment in segments_to_use:
                    # Usar caminho absoluto e escapar caracteres especiais
                    abs_path = str(segment.filepath.absolute()).replace('\\', '/')
                    concat_file.write(f"file '{abs_path}'\n")
                
                concat_file_path = concat_file.name
            
            try:
                # Comando FFmpeg para concatenação rápida
                cmd = [
                    "ffmpeg",
                    "-y",  # Sobrescrever arquivo
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_file_path,
                    "-c", "copy",  # Copiar streams sem reencode
                    "-avoid_negative_ts", "make_zero",
                    str(clip_path)
                ]
                
                # Executar comando
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    return True
                else:
                    self.logger.log_camera_event(
                        segments[0].filename.split('_')[0], "ffmpeg_concat_error",
                        f"Erro na concatenação: {result.stderr}",
                        level="ERROR"
                    )
                    return False
                    
            finally:
                # Remover arquivo temporário
                try:
                    os.unlink(concat_file_path)
                except:
                    pass
                    
        except Exception as e:
            self.logger.log_error("fast_clip_generation", e)
            return False
    
    def _generate_clip_precise(self, segments: List, clip_path: Path, 
                              trigger_time: datetime, duration: float) -> bool:
        """
        Gera clipe em modo preciso (com reencode parcial para duração exata)
        
        Args:
            segments: Lista de segmentos
            clip_path: Caminho do arquivo de saída
            trigger_time: Momento do gatilho
            duration: Duração desejada
            
        Returns:
            True se gerado com sucesso
        """
        try:
            # Calcular tempo de início do clipe
            clip_start_time = trigger_time - timedelta(seconds=duration)
            
            # Encontrar segmentos que cobrem o período necessário
            total_duration_needed = duration + 10  # Buffer extra para garantir cobertura
            segments_needed = math.ceil(total_duration_needed / self.config.chunk_duration)
            segments_to_use = segments[-segments_needed:] if len(segments) >= segments_needed else segments
            
            if not segments_to_use:
                return False
            
            # Primeira etapa: concatenar segmentos
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_concat:
                temp_concat_path = temp_concat.name
            
            try:
                # Concatenar segmentos
                if not self._concatenate_segments(segments_to_use, temp_concat_path):
                    return False
                
                # Segunda etapa: cortar com duração exata
                # Calcular offset de início dentro do vídeo concatenado
                first_segment_time = segments_to_use[0].timestamp
                start_offset = max(0, (clip_start_time - first_segment_time).total_seconds())
                
                # Comando FFmpeg para corte preciso
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", temp_concat_path,
                    "-ss", str(start_offset),
                    "-t", str(duration),
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "23",
                    "-c:a", "aac",
                    "-avoid_negative_ts", "make_zero",
                    str(clip_path)
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                return result.returncode == 0
                
            finally:
                # Remover arquivo temporário
                try:
                    os.unlink(temp_concat_path)
                except:
                    pass
                    
        except Exception as e:
            self.logger.log_error("precise_clip_generation", e)
            return False
    
    def _concatenate_segments(self, segments: List, output_path: str) -> bool:
        """
        Concatena segmentos em um arquivo temporário
        
        Args:
            segments: Lista de segmentos
            output_path: Caminho do arquivo de saída
            
        Returns:
            True se concatenado com sucesso
        """
        try:
            # Criar arquivo de lista para concatenação
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as concat_file:
                for segment in segments:
                    abs_path = str(segment.filepath.absolute()).replace('\\', '/')
                    concat_file.write(f"file '{abs_path}'\n")
                
                concat_file_path = concat_file.name
            
            try:
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_file_path,
                    "-c", "copy",
                    output_path
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                return result.returncode == 0
                
            finally:
                try:
                    os.unlink(concat_file_path)
                except:
                    pass
                    
        except Exception as e:
            self.logger.log_error("segment_concatenation", e)
            return False
    
    def generate_clips_all_cameras(self, trigger_time: datetime, 
                                  duration: Optional[float] = None) -> Dict[str, bool]:
        """
        Gera clipes para todas as câmeras
        
        Args:
            trigger_time: Momento do gatilho
            duration: Duração do clipe
            
        Returns:
            Dicionário com resultado para cada câmera
        """
        results = {}
        
        for camera_info in self.config.get_all_cameras_info():
            camera_id = camera_info["name"]
            
            try:
                success = self.generate_clip(camera_id, trigger_time, duration)
                results[camera_id] = success
                
            except Exception as e:
                self.logger.log_error("multi_camera_clip", e, {
                    "camera_id": camera_id
                })
                results[camera_id] = False
        
        return results
    
    def cleanup_old_clips(self, max_age_days: int = 30):
        """
        Remove clipes antigos para liberar espaço
        
        Args:
            max_age_days: Idade máxima dos clipes em dias
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(days=max_age_days)
            clips_removed = 0
            bytes_freed = 0
            
            for clip_file in self.config.clips_dir.glob("*_clip_*.mp4"):
                try:
                    # Verificar idade do arquivo
                    file_time = datetime.fromtimestamp(clip_file.stat().st_mtime)
                    
                    if file_time < cutoff_time:
                        file_size = clip_file.stat().st_size
                        clip_file.unlink()
                        
                        clips_removed += 1
                        bytes_freed += file_size
                        
                        self.logger.log_system_event(
                            "old_clip_removed",
                            f"Clipe antigo removido: {clip_file.name}",
                            {
                                "file_age_days": (datetime.utcnow() - file_time).days,
                                "file_size_bytes": file_size
                            }
                        )
                        
                except Exception as e:
                    self.logger.log_error("clip_cleanup", e, {
                        "file": str(clip_file)
                    })
            
            if clips_removed > 0:
                self.logger.log_system_event(
                    "clip_cleanup_completed",
                    f"Limpeza concluída: {clips_removed} clipes removidos",
                    {
                        "clips_removed": clips_removed,
                        "bytes_freed": bytes_freed,
                        "max_age_days": max_age_days
                    }
                )
                
        except Exception as e:
            self.logger.log_error("clip_cleanup", e)
    
    def get_generation_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas de geração de clipes
        
        Returns:
            Dicionário com estatísticas
        """
        avg_processing_time = (
            self.total_processing_time / self.clips_generated 
            if self.clips_generated > 0 else 0
        )
        
        return {
            "clips_generated": self.clips_generated,
            "total_processing_time_seconds": self.total_processing_time,
            "average_processing_time_seconds": avg_processing_time,
            "clips_directory": str(self.config.clips_dir),
            "current_clips_count": len(list(self.config.clips_dir.glob("*_clip_*.mp4")))
        }
