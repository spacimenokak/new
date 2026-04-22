"""Producer для отправки сообщений в брокеры."""

import time
import threading
from typing import Optional, Callable
from abc import ABC, abstractmethod

import pika
import redis

from config import RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_QUEUE
from config import REDIS_HOST, REDIS_PORT, REDIS_QUEUE
from utils import generate_payload


class BaseProducer(ABC):
    """Базовый класс Producer."""
    
    @abstractmethod
    def connect(self):
        pass
    
    @abstractmethod
    def send_message(self, payload: bytes) -> bool:
        pass
    
    @abstractmethod
    def get_queue_size(self) -> int:
        pass
    
    @abstractmethod
    def close(self):
        pass


class RabbitMQProducer(BaseProducer):
    """Producer для RabbitMQ (ОПТИМИЗИРОВАННЫЙ)."""
    
    def __init__(self):
        self.connection: Optional[pika.BlockingConnection] = None
        self.channel: Optional[pika.channel.Channel] = None
        self._queue_name = RABBITMQ_QUEUE
        self._error_count = 0
        
    def connect(self):
        """Подключение к RabbitMQ."""
        max_retries = 10
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                credentials = pika.PlainCredentials('guest', 'guest')
                parameters = pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    port=RABBITMQ_PORT,
                    credentials=credentials,
                    heartbeat=60,
                    blocked_connection_timeout=300,
                    connection_attempts=3,
                    retry_delay=1
                )
                self.connection = pika.BlockingConnection(parameters)
                self.channel = self.connection.channel()
                
                # Создаем очередь (НЕ durable для скорости)
                self.channel.queue_declare(
                    queue=self._queue_name,
                    durable=False,
                    auto_delete=True
                )
                
                # НЕ включаем подтверждения!
                # self.channel.confirm_delivery()  # ЗАКОММЕНТИРОВАНО
                
                print(f"    ✓ Подключено к RabbitMQ")
                return
                
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise Exception(f"Не удалось подключиться к RabbitMQ: {e}")
        
    def send_message(self, payload: bytes) -> bool:
        """Отправка сообщения (fire-and-forget для скорости)."""
        try:
            self.channel.basic_publish(
                exchange='',
                routing_key=self._queue_name,
                body=payload,
                properties=pika.BasicProperties(
                    delivery_mode=1,  # НЕ persistent
                )
                # БЕЗ mandatory=True
            )
            return True
        except Exception as e:
            self._error_count += 1
            if self._error_count % 1000 == 0:
                print(f"    RabbitMQ send error: {e}")
            return False
    
    def get_queue_size(self) -> int:
        """Получение размера очереди."""
        try:
            queue_info = self.channel.queue_declare(
                queue=self._queue_name,
                passive=True
            )
            return queue_info.method.message_count
        except:
            return 0
    
    def close(self):
        """Закрытие соединения."""
        if self.connection and self.connection.is_open:
            self.connection.close()


class RedisProducer(BaseProducer):
    """Producer для Redis."""
    
    def __init__(self):
        self.client: Optional[redis.Redis] = None
        self._queue_name = REDIS_QUEUE
        self._error_count = 0
        
    def connect(self):
        """Подключение к Redis."""
        max_retries = 5
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                self.client = redis.Redis(
                    host=REDIS_HOST,
                    port=REDIS_PORT,
                    decode_responses=False,
                    socket_connect_timeout=5,
                    socket_keepalive=True
                )
                self.client.ping()
                print(f"    ✓ Подключено к Redis")
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise Exception(f"Не удалось подключиться к Redis: {e}")
        
    def send_message(self, payload: bytes) -> bool:
        """Отправка сообщения в список."""
        try:
            self.client.rpush(self._queue_name, payload)
            return True
        except Exception as e:
            self._error_count += 1
            if self._error_count % 1000 == 0:
                print(f"    Redis send error: {e}")
            return False
    
    def get_queue_size(self) -> int:
        """Получение размера очереди."""
        try:
            return self.client.llen(self._queue_name)
        except:
            return 0
    
    def close(self):
        """Закрытие соединения."""
        if self.client:
            self.client.close()


class ProducerWorker:
    """Worker для отправки сообщений."""
    
    def __init__(
        self,
        producer: BaseProducer,
        payload: bytes,
        rate_per_second: int,
        duration: float,
        on_sent_callback: Optional[Callable] = None
    ):
        self.producer = producer
        self.payload = payload
        self.rate_per_second = rate_per_second
        self.duration = duration
        self.on_sent_callback = on_sent_callback
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._messages_sent = 0
        self._messages_failed = 0
        
    @property
    def messages_sent(self) -> int:
        return self._messages_sent
    
    @property
    def messages_failed(self) -> int:
        return self._messages_failed
    
    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._send_loop)
        self._thread.start()
    
    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def _send_loop(self):
        """Упрощенный цикл отправки."""
        start_time = time.time()
        messages_sent_in_second = 0
        second_start = start_time
        
        while self._running and (time.time() - start_time) < self.duration:
            current_time = time.time()
            
            # Сброс счетчика каждую секунду
            if current_time - second_start >= 1.0:
                messages_sent_in_second = 0
                second_start = current_time
            
            # Отправляем, если не превысили лимит
            if messages_sent_in_second < self.rate_per_second:
                if self.producer.send_message(self.payload):
                    self._messages_sent += 1
                    messages_sent_in_second += 1
                    if self.on_sent_callback:
                        self.on_sent_callback()
                else:
                    self._messages_failed += 1
            else:
                # Ждем следующей секунды
                time.sleep(0.001)


def run_producers(
    producer_class,
    num_workers: int,
    payload_size: int,
    rate_per_second: int,
    duration: float,
    on_sent_callback: Optional[Callable] = None
) -> tuple:
    """Запуск нескольких producer worker'ов."""
    payload = generate_payload(payload_size)
    rate_per_worker = max(1, rate_per_second // num_workers)
    
    producers = []
    workers = []
    
    for _ in range(num_workers):
        producer = producer_class()
        producer.connect()
        producers.append(producer)
        
        worker = ProducerWorker(
            producer=producer,
            payload=payload,
            rate_per_second=rate_per_worker,
            duration=duration,
            on_sent_callback=on_sent_callback
        )
        workers.append(worker)
        worker.start()
    
    return producers, workers