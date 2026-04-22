"""Общие настройки для бенчмарка."""

# Настройки подключения
RABBITMQ_HOST = 'localhost'
RABBITMQ_PORT = 5672
RABBITMQ_QUEUE = 'benchmark_queue'

REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_QUEUE = 'benchmark_queue'

# Параметры тестирования
MESSAGE_SIZES = [128, 1024, 10240, 102400]  # в байтах: 128B, 1KB, 10KB, 100KB
RATES = [1000, 5000, 10000]  # msg/sec
TEST_DURATION = 30  # секунд на каждый тест

# Количество воркеров
NUM_PRODUCERS = 2
NUM_CONSUMERS = 2