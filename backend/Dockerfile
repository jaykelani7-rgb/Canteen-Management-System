FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1 PGSSLROOTCERT=/etc/ssl/certs/ca-certificates.crt
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --uid 10001 --create-home canteen && test -r /etc/ssl/certs/ca-certificates.crt
COPY --chown=canteen:canteen backend/ .
USER canteen
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=6s --start-period=30s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/api/health', timeout=5)"
CMD ["python", "start_server.py"]
