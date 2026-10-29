# ===== 后端 =====
FROM python:3.13-slim

WORKDIR /app

# 装系统依赖（PyMuPDF 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 装 pip 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 装 Ollama（CPU 推理）
# Ollama 让用户自己启动或用 host 模式

# 复制代码
COPY . .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
