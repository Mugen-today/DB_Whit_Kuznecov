FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --no-create-home backend
RUN mkdir -p /var/lib/gis-imports && chown 10001:10001 /var/lib/gis-imports
COPY app ./app
USER 10001
CMD ["python", "-m", "app.main"]
