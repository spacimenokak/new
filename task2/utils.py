"""Вспомогательные функции."""

import time
import psutil
import threading
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from collections import deque


@dataclass
class BenchmarkResult:
    """Результаты одного теста."""
    broker: str
    message_size: int
    target_rate: int
    duration: float
    
    messages_sent: int = 0
    messages_received: int = 0
    messages_failed: int = 0
    
    latencies: List[float] = field(default_factory=list)
    
    cpu_usage: List[float] = field(default_factory=list)
    memory_usage: List[float] = field(default_factory=list)
    queue_size_history: List[int] = field(default_factory=list)
    
    error_message: Optional[str] = None
    
    @property
    def actual_rate(self) -> float:
        """Фактическая скорость отправки."""
        return self.messages_sent / self.duration if self.duration > 0 else 0
    
    @property
    def success_rate(self) -> float:
        """Процент успешно обработанных сообщений."""
        return (self.messages_received / self.messages_sent * 100) if self.messages_sent > 0 else 0
    
    @property
    def avg_latency(self) -> float:
        """Средняя задержка в миллисекундах."""
        return (sum(self.latencies) / len(self.latencies) * 1000) if self.latencies else 0
    
    @property
    def p95_latency(self) -> float:
        """95-й перцентиль задержки в миллисекундах."""
        if not self.latencies:
            return 0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[idx] * 1000
    
    @property
    def p99_latency(self) -> float:
        """99-й перцентиль задержки в миллисекундах."""
        if not self.latencies:
            return 0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[idx] * 1000
    
    @property
    def avg_cpu(self) -> float:
        """Средняя загрузка CPU."""
        return sum(self.cpu_usage) / len(self.cpu_usage) if self.cpu_usage else 0
    
    @property
    def avg_memory_mb(self) -> float:
        """Среднее использование памяти в MB."""
        return sum(self.memory_usage) / len(self.memory_usage) if self.memory_usage else 0
    
    @property
    def max_queue_size(self) -> int:
        """Максимальный размер очереди."""
        return max(self.queue_size_history) if self.queue_size_history else 0


class MetricsCollector:
    """Сборщик метрик в реальном времени."""
    
    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Метрики
        self.cpu_samples: List[float] = []
        self.memory_samples: List[float] = []
        self.queue_sizes: List[int] = []
        
        self._queue_size_callback = None
    
    def set_queue_size_callback(self, callback):
        """Установка callback для получения размера очереди."""
        self._queue_size_callback = callback
    
    def start(self):
        """Запуск сбора метрик."""
        self._running = True
        self._thread = threading.Thread(target=self._collect_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Остановка сбора метрик."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
    
    def _collect_loop(self):
        """Основной цикл сбора метрик."""
        process = psutil.Process()
        
        while self._running:
            # CPU и память текущего процесса
            self.cpu_samples.append(process.cpu_percent(interval=None))
            self.memory_samples.append(process.memory_info().rss / 1024 / 1024)  # MB
            
            # Размер очереди
            if self._queue_size_callback:
                try:
                    self.queue_sizes.append(self._queue_size_callback())
                except:
                    pass
            
            time.sleep(self.interval)
    
    def get_results(self) -> tuple:
        """Получение собранных метрик."""
        return self.cpu_samples, self.memory_samples, self.queue_sizes


class LatencyTracker:
    """Трекер задержек."""
    
    def __init__(self, max_samples: int = 100000):
        self.max_samples = max_samples
        self.latencies: deque = deque(maxlen=max_samples)
        self._lock = threading.Lock()
    
    def add(self, latency: float):
        """Добавление замера задержки."""
        with self._lock:
            self.latencies.append(latency)
    
    def get_all(self) -> List[float]:
        """Получение всех замеров."""
        with self._lock:
            return list(self.latencies)
    
    def clear(self):
        """Очистка."""
        with self._lock:
            self.latencies.clear()


def generate_payload(size_bytes: int) -> bytes:
    """Генерация сообщения заданного размера."""
    # Используем повторяющийся паттерн для реалистичности
    base = b"BENCHMARK_PAYLOAD_" * 10  # ~190 байт
    payload = base * ((size_bytes // len(base)) + 1)
    return payload[:size_bytes]