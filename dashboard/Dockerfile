FROM python:3.12-slim
WORKDIR /app
COPY app.py .
COPY components ./components
USER 10001
CMD ["python", "app.py"]
