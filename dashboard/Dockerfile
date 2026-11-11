FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 HOME=/tmp STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home appuser
COPY app.py .
COPY components ./components
USER 10001
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]