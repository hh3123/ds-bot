FROM python:3.12-slim

WORKDIR /app

# Лёгкий CPU-torch отдельным шагом: 200 МБ вместо 2.5 ГБ CUDA-сборки
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Запекаем модель Silero v5.1 в образ: контейнер стартует без долгих скачиваний
RUN python -c "import torch; torch.hub.load('snakers4/silero-models', 'silero_tts', language='ru', speaker='v5_1_ru', trust_repo=True)" \
    && cp -r /root/.cache/torch /app/torch_cache
ENV TORCH_HOME=/app/torch_cache

# HF Spaces health/порт
ENV HEALTH_PORT=7860
EXPOSE 7860

CMD ["python", "bot.py"]
