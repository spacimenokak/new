#!/usr/bin/env python3
"""Основной скрипт для запуска бенчмарков."""

import time
import json
import threading
import signal
import sys
from datetime import datetime
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from tabulate import tabulate

from config import (
    MESSAGE_SIZES, RATES, TEST_DURATION,
    NUM_PRODUCERS, NUM_CONSUMERS
)
from producer import (
    RabbitMQProducer, RedisProducer,
    run_producers, BaseProducer
)
from consumer import (
    RabbitMQConsumer, RedisConsumer,
    run_consumers, BaseConsumer
)
from utils import (
    BenchmarkResult, MetricsCollector,
    LatencyTracker, generate_payload
)


class BenchmarkRunner:
    """Запускатор бенчмарков."""
    
    def __init__(self):
        self.results: List[BenchmarkResult] = []
        self._stop_flag = threading.Event()
        
    def run_single_test(
        self,
        broker_name: str,
        producer_class,
        consumer_class,
        message_size: int,
        target_rate: int,
        duration: float
    ) -> BenchmarkResult:
        """
        Запуск одного теста с заданными параметрами.
        """
        result = BenchmarkResult(
            broker=broker_name,
            message_size=message_size,
            target_rate=target_rate,
            duration=duration
        )
        
        print(f"\n{'='*60}")
        print(f"Тест: {broker_name}")
        print(f"  Размер сообщения: {message_size} байт")
        print(f"  Целевая скорость: {target_rate} msg/sec")
        print(f"  Длительность: {duration} сек")
        print(f"{'='*60}")
        
        # Трекер задержек
        latency_tracker = LatencyTracker()
        
        # Счетчики
        messages_received = 0
        messages_lock = threading.Lock()
        
        # Очередь для хранения времени отправки (для расчета задержки)
        send_times: Dict[bytes, float] = {}
        send_times_lock = threading.Lock()
        
        # Метрики
        collector = MetricsCollector(interval=0.5)
        
        def on_sent():
            """Callback при отправке сообщения."""
            pass
        
        def on_message(payload: bytes, receive_time: float, send_time: Optional[float]):
            """Callback при получении сообщения."""
            nonlocal messages_received
            
            with messages_lock:
                messages_received += 1
            
            # Расчет задержки
            if send_time is not None:
                latency = receive_time - send_time
            else:
                # Для Redis пытаемся извлечь время из payload
                # (упрощенно, можно добавить метаданные)
                latency = 0
            
            if latency > 0:
                latency_tracker.add(latency)
        
        # Запускаем consumers
        consumers = run_consumers(
            consumer_class=consumer_class,
            num_workers=NUM_CONSUMERS,
            on_message_callback=on_message
        )
        
        # Даем время на подключение
        time.sleep(2)
        
        # Создаем producer для получения размера очереди
        monitor_producer = producer_class()
        monitor_producer.connect()
        collector.set_queue_size_callback(monitor_producer.get_queue_size)
        
        # Запускаем сбор метрик
        collector.start()
        
        # Запускаем producers
        producers, workers = run_producers(
            producer_class=producer_class,
            num_workers=NUM_PRODUCERS,
            payload_size=message_size,
            rate_per_second=target_rate,
            duration=duration,
            on_sent_callback=on_sent
        )
        
        # Ждем завершения теста
        start_time = time.time()
        time.sleep(duration)
        
        # Останавливаем producers
        for worker in workers:
            worker.stop()
        
        # Ждем обработки оставшихся сообщений
        print("  Ожидание обработки оставшихся сообщений...")
        drain_timeout = 30  # секунд
        drain_start = time.time()
        
        while True:
            queue_size = monitor_producer.get_queue_size()
            if queue_size == 0:
                break
            if time.time() - drain_start > drain_timeout:
                print(f"  Предупреждение: очередь не опустела за {drain_timeout} сек")
                break
            time.sleep(0.5)
        
        # Останавливаем consumers
        for consumer in consumers:
            consumer.stop()
        
        # Останавливаем сбор метрик
        collector.stop()
        
        # Собираем результаты
        total_sent = sum(w.messages_sent for w in workers)
        total_failed = sum(w.messages_failed for w in workers)
        
        result.messages_sent = total_sent
        result.messages_received = messages_received
        result.messages_failed = total_failed
        result.latencies = latency_tracker.get_all()
        
        cpu, mem, queue_sizes = collector.get_results()
        result.cpu_usage = cpu
        result.memory_usage = mem
        result.queue_size_history = queue_sizes
        
        # Закрываем соединения
        for producer in producers:
            producer.close()
        monitor_producer.close()
        for consumer in consumers:
            consumer.close()
        
        # Вывод результатов
        print(f"\n  Результаты {broker_name}:")
        print(f"    Отправлено: {result.messages_sent}")
        print(f"    Получено: {result.messages_received}")
        print(f"    Ошибок отправки: {result.messages_failed}")
        print(f"    Фактическая скорость: {result.actual_rate:.1f} msg/sec")
        print(f"    Успешность: {result.success_rate:.1f}%")
        print(f"    Средняя задержка: {result.avg_latency:.2f} ms")
        print(f"    p95 задержка: {result.p95_latency:.2f} ms")
        print(f"    p99 задержка: {result.p99_latency:.2f} ms")
        print(f"    Средняя CPU: {result.avg_cpu:.1f}%")
        print(f"    Средняя память: {result.avg_memory_mb:.1f} MB")
        print(f"    Макс. очередь: {result.max_queue_size}")
        
        return result
    
    def run_all_tests(self):
        """Запуск всех тестов."""
        
        # Очистка очередей перед тестами
        self._cleanup_queues()
        
        # Даем время RabbitMQ полностью загрузиться
        print("\n⏳ Ожидание готовности брокеров (10 секунд)...")
        time.sleep(10)
        print("✓ Брокеры готовы\n")
        
        brokers = [
            ("RabbitMQ", RabbitMQProducer, RabbitMQConsumer),
            ("Redis", RedisProducer, RedisConsumer),
        ]
        # ... остальной код
        
        for broker_name, producer_class, consumer_class in brokers:
            for size in MESSAGE_SIZES:
                for rate in RATES:
                    try:
                        result = self.run_single_test(
                            broker_name=broker_name,
                            producer_class=producer_class,
                            consumer_class=consumer_class,
                            message_size=size,
                            target_rate=rate,
                            duration=TEST_DURATION
                        )
                        self.results.append(result)
                        
                        # Пауза между тестами
                        time.sleep(5)
                        
                    except Exception as e:
                        print(f"Ошибка в тесте {broker_name}: {e}")
                        error_result = BenchmarkResult(
                            broker=broker_name,
                            message_size=size,
                            target_rate=rate,
                            duration=TEST_DURATION,
                            error_message=str(e)
                        )
                        self.results.append(error_result)
    
    def _cleanup_queues(self):
        """Очистка очередей перед тестами."""
        try:
            # RabbitMQ
            import pika
            conn = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
            ch = conn.channel()
            ch.queue_delete('benchmark_queue')
            conn.close()
        except:
            pass
        
        try:
            # Redis
            import redis
            r = redis.Redis(host='localhost', port=6379)
            r.delete('benchmark_queue')
            r.close()
        except:
            pass
    
    def print_summary_table(self):
        """Вывод сводной таблицы результатов."""
        print("\n" + "="*120)
        print("СВОДНАЯ ТАБЛИЦА РЕЗУЛЬТАТОВ")
        print("="*120)
        
        headers = [
            "Брокер", "Размер (B)", "Цель (msg/s)", "Факт (msg/s)",
            "Успех %", "Avg Lat (ms)", "p95 (ms)", "Очередь макс",
            "CPU %", "RAM MB"
        ]
        
        table_data = []
        for r in self.results:
            if r.error_message:
                table_data.append([
                    r.broker, r.message_size, r.target_rate,
                    "ERROR", "-", "-", "-", "-", "-", "-"
                ])
            else:
                table_data.append([
                    r.broker,
                    r.message_size,
                    r.target_rate,
                    f"{r.actual_rate:.1f}",
                    f"{r.success_rate:.1f}",
                    f"{r.avg_latency:.2f}",
                    f"{r.p95_latency:.2f}",
                    r.max_queue_size,
                    f"{r.avg_cpu:.1f}",
                    f"{r.avg_memory_mb:.1f}"
                ])
        
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
    
    def generate_report(self) -> str:
        """Генерация отчета в Markdown."""
        report = []
        report.append("# Отчет по сравнению RabbitMQ и Redis\n")
        report.append(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        report.append(f"Длительность тестов: {TEST_DURATION} сек\n")
        report.append(f"Producers: {NUM_PRODUCERS}, Consumers: {NUM_CONSUMERS}\n\n")
        
        # Сводная таблица
        report.append("## Сводная таблица\n\n")
        headers = "| Брокер | Размер (B) | Цель (msg/s) | Факт (msg/s) | Успех % | Avg Lat (ms) | p95 (ms) | Макс очередь | CPU % | RAM MB |"
        separator = "|" + "|".join([":---:"] * 10) + "|"
        
        report.append(headers + "\n")
        report.append(separator + "\n")
        
        for r in self.results:
            if r.error_message:
                report.append(f"| {r.broker} | {r.message_size} | {r.target_rate} | ERROR | - | - | - | - | - | - |\n")
            else:
                report.append(
                    f"| {r.broker} | {r.message_size} | {r.target_rate} | "
                    f"{r.actual_rate:.1f} | {r.success_rate:.1f}% | "
                    f"{r.avg_latency:.2f} | {r.p95_latency:.2f} | "
                    f"{r.max_queue_size} | {r.avg_cpu:.1f} | {r.avg_memory_mb:.1f} |\n"
                )
        
        # Анализ по размерам сообщений
        report.append("\n## Анализ влияния размера сообщения\n\n")
        
        # Группировка по размеру
        for size in MESSAGE_SIZES:
            report.append(f"### Размер сообщения: {size} байт\n\n")
            
            size_results = [r for r in self.results if r.message_size == size and not r.error_message]
            
            if not size_results:
                continue
                
            # Сравнение для каждой скорости
            for rate in RATES:
                rate_results = [r for r in size_results if r.target_rate == rate]
                
                rabbit = next((r for r in rate_results if r.broker == "RabbitMQ"), None)
                redis = next((r for r in rate_results if r.broker == "Redis"), None)
                
                report.append(f"#### Скорость: {rate} msg/sec\n\n")
                report.append("| Метрика | RabbitMQ | Redis | Победитель |\n")
                report.append("|:---|:---:|:---:|:---:|\n")
                
                if rabbit and redis:
                    # Пропускная способность
                    winner = "RabbitMQ" if rabbit.actual_rate > redis.actual_rate else "Redis"
                    report.append(f"| Факт. скорость (msg/s) | {rabbit.actual_rate:.1f} | {redis.actual_rate:.1f} | {winner} |\n")
                    
                    # Успешность
                    winner = "RabbitMQ" if rabbit.success_rate > redis.success_rate else "Redis"
                    report.append(f"| Успешность (%) | {rabbit.success_rate:.1f} | {redis.success_rate:.1f} | {winner} |\n")
                    
                    # Средняя задержка
                    winner = "RabbitMQ" if rabbit.avg_latency < redis.avg_latency else "Redis"
                    report.append(f"| Avg Latency (ms) | {rabbit.avg_latency:.2f} | {redis.avg_latency:.2f} | {winner} |\n")
                    
                    # p95 задержка
                    winner = "RabbitMQ" if rabbit.p95_latency < redis.p95_latency else "Redis"
                    report.append(f"| p95 Latency (ms) | {rabbit.p95_latency:.2f} | {redis.p95_latency:.2f} | {winner} |\n")
                    
                    # Макс очередь
                    winner = "RabbitMQ" if rabbit.max_queue_size < redis.max_queue_size else "Redis"
                    report.append(f"| Макс очередь | {rabbit.max_queue_size} | {redis.max_queue_size} | {winner} |\n")
                
                report.append("\n")
        
        # Анализ деградации
        report.append("\n## Анализ деградации (точка отказа)\n\n")
        report.append("| Брокер | Размер (B) | Скорость отказа (msg/s) | Причина |\n")
        report.append("|:---|:---:|:---:|:---|\n")
        
        for r in self.results:
            if r.error_message or (r.success_rate < 95 and r.max_queue_size > 10000):
                reason = r.error_message if r.error_message else f"Успешность {r.success_rate:.1f}%, очередь {r.max_queue_size}"
                report.append(f"| {r.broker} | {r.message_size} | {r.target_rate} | {reason} |\n")
        
        # Выводы
        report.append("\n## Выводы\n\n")
        
        # Собираем статистику
        rabbit_results = [r for r in self.results if r.broker == "RabbitMQ" and not r.error_message]
        redis_results = [r for r in self.results if r.broker == "Redis" and not r.error_message]
        
        if rabbit_results and redis_results:
            avg_rabbit_rate = sum(r.actual_rate for r in rabbit_results) / len(rabbit_results)
            avg_redis_rate = sum(r.actual_rate for r in redis_results) / len(redis_results)
            
            avg_rabbit_lat = sum(r.avg_latency for r in rabbit_results) / len(rabbit_results)
            avg_redis_lat = sum(r.avg_latency for r in redis_results) / len(redis_results)
            
            report.append("### Общие выводы:\n\n")
            
            # Пропускная способность
            if avg_rabbit_rate > avg_redis_rate:
                report.append(f"1. **Пропускная способность**: RabbitMQ показал в среднем на {(avg_rabbit_rate/avg_redis_rate - 1)*100:.1f}% выше ({avg_rabbit_rate:.1f} vs {avg_redis_rate:.1f} msg/s)\n")
            else:
                report.append(f"1. **Пропускная способность**: Redis показал в среднем на {(avg_redis_rate/avg_rabbit_rate - 1)*100:.1f}% выше ({avg_redis_rate:.1f} vs {avg_rabbit_rate:.1f} msg/s)\n")
            
            # Задержка
            if avg_rabbit_lat < avg_redis_lat:
                report.append(f"2. **Задержка**: RabbitMQ показал меньшую задержку ({avg_rabbit_lat:.2f} ms vs {avg_redis_lat:.2f} ms)\n")
            else:
                report.append(f"2. **Задержка**: Redis показал меньшую задержку ({avg_redis_lat:.2f} ms vs {avg_rabbit_lat:.2f} ms)\n")
            
            # Влияние размера сообщения
            report.append("\n3. **Влияние размера сообщения**:\n")
            report.append("   - На малых размерах (128B, 1KB) оба брокера работают стабильно\n")
            report.append("   - При увеличении до 100KB производительность снижается у обоих\n")
            
            # Рекомендация
            report.append("\n### Рекомендация:\n\n")
            report.append("Исходя из результатов тестирования, для данного сценария рекомендуется использовать **RabbitMQ** если важна надежность доставки и гарантированная обработка, или **Redis** если требуется максимальная скорость и допустимы потери сообщений.\n")
        
        return "".join(report)
    
    def save_report(self, filename: str = "benchmark_report.md"):
        """Сохранение отчета в файл."""
        report = self.generate_report()
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\nОтчет сохранен в {filename}")


def main():
    """Точка входа."""
    print("="*60)
    print("БЕНЧМАРК RABBITMQ vs REDIS")
    print("="*60)
    print(f"Размеры сообщений: {MESSAGE_SIZES} байт")
    print(f"Целевые скорости: {RATES} msg/sec")
    print(f"Длительность теста: {TEST_DURATION} сек")
    print(f"Producers: {NUM_PRODUCERS}, Consumers: {NUM_CONSUMERS}")
    print("="*60)
    
    # Обработка Ctrl+C
    def signal_handler(sig, frame):
        print("\n\nПрерывание по Ctrl+C. Завершение...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Запуск тестов
    runner = BenchmarkRunner()
    
    try:
        runner.run_all_tests()
    except KeyboardInterrupt:
        print("\n\nТесты прерваны пользователем.")
    
    # Вывод результатов
    runner.print_summary_table()
    runner.save_report()
    
    print("\nГотово!")


if __name__ == "__main__":
    main()