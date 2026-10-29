# Một image cho cả `web` (FastAPI) và `worker` (crawler + Chromium) — design doc cloud §12.
# Image Playwright chính thức đã có Chromium + thư viện hệ thống. ARM64 (Oracle A1): kiểm tra ở P0 bằng
#   docker manifest inspect mcr.microsoft.com/playwright/python:v1.60.0-noble
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements-cloud.txt ./
RUN pip install --no-cache-dir --break-system-packages -r requirements-cloud.txt

COPY crawler ./crawler
COPY cloud ./cloud
COPY match_report.html ./

# chạy bằng user thường (pwuser có sẵn trong image Playwright); /data là volume bền vững
RUN mkdir -p /data/backups && chown -R pwuser:pwuser /data
USER pwuser
ENV DB_PATH=/data/app.db BACKUP_DIR=/data/backups

EXPOSE 8000
CMD ["uvicorn", "cloud.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
