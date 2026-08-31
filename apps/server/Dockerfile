FROM python:3.12-slim
WORKDIR /app
COPY apps/server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
CMD ["python", "-m", "uvicorn", "apps.server.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
