FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml .
COPY src ./src
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple .

COPY .env.example ./

EXPOSE 8000

CMD ["python", "-m", "src.main", "api", "--host", "0.0.0.0"]