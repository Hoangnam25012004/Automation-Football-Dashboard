# Hugging Face Docker Space — một container chạy web + worker (python -m cloud.hf_main), cổng 7860.
# Dữ liệu ở /tmp (ổ Space không bền) và được đồng bộ ra Dataset riêng tư (cloud/hfsync.py).
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp \
    HF_HOME=/tmp/hf-cache \
    DB_PATH=/tmp/matchperf/app.db \
    BACKUP_DIR=/tmp/matchperf/backups \
    TZ=Asia/Ho_Chi_Minh \
    PORT=7860

WORKDIR /app
COPY requirements-cloud.txt ./
RUN pip install --no-cache-dir --break-system-packages -r requirements-cloud.txt huggingface_hub==2.3.0

COPY crawler ./crawler
COPY cloud ./cloud
COPY match_report.html ./

# Space chạy container bằng UID 1000 — thư mục dữ liệu phải ghi được với mọi UID
RUN mkdir -p /tmp/matchperf/backups /tmp/hf-cache && chmod -R 777 /tmp/matchperf /tmp/hf-cache

EXPOSE 7860
CMD ["python", "-m", "cloud.hf_main"]
