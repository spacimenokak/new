"""Consumer для получения и обработки сообщений."""

import time
import threading
from typing import Optional, Callable
from abc import ABC, abstractmethod

import pika
import redis

from config import RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_QUEUE
from config import REDIS_HOST, REDIS_PORT, REDIS_QUEUE


class BaseConsumer(ABC):
    """Базовый класс Consumer."""
    
    @abstractmethod
    def connect(self):
        """Подключение к брокеру."""
        pass
    
    @abstractmethod
    def start_consuming(self, on_message_callback: Callable):
        """Начать потребление сообщений."""
        pass
    
    @abstractmethod
    def stop(self):
        """Остановить потребление."""
        pass
    
    @abstractmethod
    def close(self):
        """Закрыть соединение."""
        pass


class RabbitMQConsumer(BaseConsumer):
    """Consumer для RabbitMQ."""
    
    def __init__(self):
        self.connection: Optional[pika.BlockingConnection] = None
        self.channel: Optional[pika.channel.Channel] = None
        self._queue_name = RABBITMQ_QUEUE
        self._consuming = False
        self._consumer_tag: Optional[str] = None
        self._on_message: Optional[Callable] = None
        
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
                    blocked_connection_timeout=300
                )
                self.connection = pika.BlockingConnection(parameters)
                self.channel = self.connection.channel()
                
                # Создаем очередь (НЕ durable)
                self.channel.queue_declare(
                    queue=self._queue_name,
                    durable=False,
                    auto_delete=True
                )
                
                # Большой prefetch для скорости
                self.channel.basic_qos(prefetch_count=500)
                
                print(f"    ✓ Consumer подключен к RabbitMQ")
                return
                
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise Exception(f"Не удалось подключиться: {e}")
        
    def _message_handler(self, channel, method, properties, body):
        """Обработчик входящих сообщений."""
        receive_time = time.time()
        
        # Получаем время отправки из свойств или тела сообщения
        send_time = None
        if properties and properties.headers:
            send_time = properties.headers.get('send_timestamp')
        
        if self._on_message:
            self._on_message(body, receive_time, send_time)
        
        # Подтверждаем обработку
        channel.basic_ack(delivery_tag=method.delivery_tag)
    
    def start_consuming(self, on_message_callback: Callable):
        """Начать потребление."""
        self._on_message = on_message_callback
        self._consuming = True
        
        self._consumer_tag = self.channel.basic_consume(
            queue=self._queue_name,
            on_message_callback=self._message_handler,
            auto_ack=False
        )
        
        # Запускаем в отдельном потоке
        self._thread = threading.Thread(target=self._consume_loop)
        self._thread.start()
    
    def _consume_loop(self):
        """Цикл потребления с обработкой ошибок."""
        while self._consuming:
            try:
                self.connection.process_data_events(time_limit=1)
            except Exception as e:
                if self._consuming:
                    print(f"    ⚠️ RabbitMQ consume error, переподключение...")
                    try:
                        # Переподключаемся
                        time.sleep(1)
                        self.close()
                        self.connect()
                        # Перезапускаем потребление
                        if self._on_message:
                            self._consumer_tag = self.channel.basic_consume(
                                queue=self._queue_name,
                                on_message_callback=self._message_handler,
                                auto_ack=False
                            )
                    except Exception as reconnect_error:
                        print(f"    ❌ Ошибка переподключения: {reconnect_error}")
                        time.sleep(2)
    
    def stop(self):
        """Остановить потребление."""
        self._consuming = False
        if self._consumer_tag:
            try:
                self.channel.basic_cancel(self._consumer_tag)
            except:
                pass
        if hasattr(self, '_thread'):
            self._thread.join(timeout=2)
    
    def close(self):
        """Закрыть соединение."""
        if self.connection and self.connection.is_open:
            self.connection.close()


class RedisConsumer(BaseConsumer):
    """Consumer для Redis (блокирующее чтение из списка)."""
    
    def __init__(self):
        self.client: Optional[redis.Redis] = None
        self._queue_name = REDIS_QUEUE
        self._consuming = False
        self._on_message: Optional[Callable] = None
        
    def connect(self):
        """Подключение к Redis."""
        self.client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30
        )
        self.client.ping()
        
    def start_consuming(self, on_message_callback: Callable):
        """Начать потребление."""
        self._on_message = on_message_callback
        self._consuming = True
        self._thread = threading.Thread(target=self._consume_loop)
        self._thread.start()
    
    def _consume_loop(self):
        """Цикл потребления с блокирующим чтением."""
        while self._consuming:
            try:
                # Блокирующее чтение с таймаутом 1 секунда
                result = self.client.blpop(self._queue_name, timeout=1)
                
                if result:
                    _, payload = result
                    receive_time = time.time()
                    
                    if self._on_message:
                        self._on_message(payload, receive_time, None)
                        
            except Exception as e:
                if self._consuming:
                    print(f"Redis consume error: {e}")
                    time.sleep(0.1)
    
    def stop(self):
        """Остановить потребление."""
        self._consuming = False
        if hasattr(self, '_thread'):
            self._thread.join(timeout=2)
    
    def close(self):
        """Закрыть соединение."""
        if self.client:
            self.client.close()


def run_consumers(
    consumer_class,
    num_workers: int,
    on_message_callback: Callable
) -> list:
    """
    Запуск нескольких consumer worker'ов.
    
    Returns:
        list: Список consumer'ов
    """
    consumers = []
    
    for _ in range(num_workers):
        consumer = consumer_class()
        consumer.connect()
        consumer.start_consuming(on_message_callback)
        consumers.append(consumer)
    
    return consumers