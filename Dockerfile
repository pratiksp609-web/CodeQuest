# CodeQuest: web app + code judge in one image.
# Build:  docker build -t codequest .            (all judge languages, ~1.5 GB)
#         docker build --build-arg FULL=0 -t codequest .   (Python, C, C++, Java, JavaScript only)
FROM python:3.12-slim-bookworm

ARG FULL=1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    APP_ENV=production JUDGE_RUN_AS=judge JUDGE_NO_NETWORK=true PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ libc6-dev openjdk-17-jdk-headless nodejs \
    && if [ "$FULL" = "1" ]; then apt-get install -y --no-install-recommends \
        golang-go php-cli rustc mono-mcs mono-runtime; fi \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --no-create-home --shell /usr/sbin/nologin judge

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
# The app runs as root so it can drop each submission to the unprivileged `judge` user.
# Locking the app folder means submitted code can't read the source or local files.
RUN chmod 700 /app && rm -f learnopt.db risk_model.joblib

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/healthz')"
ENTRYPOINT ["./docker-entrypoint.sh"]
