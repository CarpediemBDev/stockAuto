# 1단계: Python Base Image 사용
FROM python:3.12-slim

# 작업 디렉터리 설정
WORKDIR /app

# 시스템 의존성 설치 (필요한 경우)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 파이썬 의존성 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 소스코드 전체 복사
COPY . .

ENV APP_ENV=prod
ENV PORT=8000

# 구글 클라우드 런은 포트 8080을 기본 포트로 매핑하거나, $PORT 환경변수를 주입합니다.
# Uvicorn이 쉘 환경변수 $PORT를 동적으로 받아 구동되도록 CMD를 설정합니다.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
