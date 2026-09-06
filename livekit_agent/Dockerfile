FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir uv \
    && uv pip install --system --no-cache -r requirements.txt

COPY agent.py ./

CMD ["python", "agent.py", "start"]
