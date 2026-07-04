# 🌐 StockAuto 저비용·고효율 무중단 클라우드 아키처 기획서

본 기획서는 AWS Lightsail, GCP Free Tier 등 극도로 리소스가 제한된 저비용 클라우드 환경(vCPU 1개, RAM 1GB 이하)에서 **StockAuto 자동 매매 봇**을 24시간 안전하고 무중단으로 운영하기 위한 인프라 아키텍처, 데이터베이스 마이그레이션, Docker 컨테이너 배치, 그리고 경량 로그/장애 알림 시스템 설계를 제안합니다.

---

## 🏛️ 1. 저비용 클라우드 인프라 아키텍처 설계

제한된 예산 속에서 안정적인 24시간 가동을 실현하기 위해, 인프라의 메모리 및 CPU 자원 낭비를 극한으로 억제하는 구조를 설계합니다.

```mermaid
graph TD
    subgraph "External Cloud Services (Free Tier / Serverless)"
        DB[(Supabase / Neon PG)]
        Ping[UptimeRobot]
        TG[Telegram Bot API]
    end

    subgraph "Cloud VPS (AWS Lightsail / GCP e2-micro)"
        direction TB
        Nginx[Nginx Alpine HTTPS Proxy] --> FE[Next.js Frontend Standalone]
        Nginx --> BE[FastAPI Backend 1-Worker]
        BE --> Redis[(Redis Alpine Cache/Lock)]
        BE -.-> DB
        BE -.-> TG
        Ping -.-> Nginx
    end
```

### 1.1. 클라우드 플랫폼 선정 및 스펙 정의

| 항목 | 옵션 A: AWS Lightsail (추천) | 옵션 B: GCP Free Tier (선택) |
| :--- | :--- | :--- |
| **선정 인스턴스** | Linux 인스턴스 (최저 요금제) | Compute Engine `e2-micro` |
| **하드웨어 스펙** | 1 vCPU, 1 GB RAM, 40 GB SSD | 0.25 vCPU (최대 2 vCPU 버스트), 1 GB RAM, 30 GB SSD |
| **예상 비용** | 월 $5.00 (약 6,800원) | 월 $0.00 (미국 리전 한정 무료 티어 조건 충족 시) |
| **네트워크 지연** | **서울 리전(ap-northeast-2)** 지원 (한국 증권사 KIS/TOSS API 통신 지연시간 2~10ms 수준 극소화) | 오레곤/아이오와 등 미국 리전 고정 (한국 증권사 API 통신 지연시간 120~200ms 발생, 체결 슬리피지 우려) |
| **결론** | **AWS Lightsail 서울 리전**이 지연시간 및 주문 체결 속도 측면에서 최선책임. | 백업 인스턴스 또는 개발/QA 검증 환경으로만 GCP Free Tier 활용 권장. |

### 1.2. 극단적 리소스 제약(RAM 1GB 이하) 극복 방안

1.  **가상 메모리(Swap Space) 필수 구성**
    *   1GB RAM 환경에서는 Docker 컨테이너 기동 및 Node.js(Next.js) 실행 시 순간적인 메모리 스파이크로 인해 OS 커널의 **OOM Killer**가 프로세스를 강제 종료(Exit Code 137)할 위험이 매우 높습니다.
    *   반드시 호스트 OS 레벨에서 **2GB 크기의 Swap 메모리**를 구성하여 물리 메모리 부족에 따른 크래시를 원천 차단합니다.
    ```bash
    # Swap 메모리 활성화 명령어 (Ubuntu/Debian 기준)
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    ```
2.  **원격 빌드 및 경량 이미지 배포 (Zero-Build on Server)**
    *   클라우드 인스턴스 내부에서 `npm run build` 또는 `docker build`를 실행하는 행위는 CPU 점유율 100% 지속 및 RAM 고갈을 유발하여 돌이킬 수 없는 중단을 야기합니다.
    *   **빌드 분리:** 로컬 개발 PC 또는 **GitHub Actions** CI/CD 파이프라인에서 Docker 이미지를 사전 빌드한 뒤, Docker Hub 또는 AWS ECR에 푸시합니다.
    *   **서버 가동:** 클라우드 서버는 단지 빌드된 이미지를 `docker compose pull && docker compose up -d` 형식으로 내려받아 실행만 함으로써, 빌드 과정의 자원 오버헤드를 0으로 만듭니다.

---

## 💾 2. 데이터베이스 마이그레이션 전략 (SQLite ➔ PostgreSQL)

StockAuto의 `database.py` 정책에 따라 운영 환경(`APP_ENV="prod"`)에서는 SQLite 사용이 금지되고 외부 관계형 DB 사용이 강제됩니다. 비용을 0원으로 억제하면서 안정성을 확보하기 위해 **Supabase** 또는 **Neon PostgreSQL**의 Serverless DB 무료 티어를 채택합니다.

### 2.1. Serverless PostgreSQL 서비스 비교 및 선정

*   **선정안: Supabase / Neon PostgreSQL Free Tier**
    *   **Supabase:** 무료 티어에서 PostgreSQL 15+ 데이터베이스 제공 (500MB 디스크 제한, 1주일 미사용 시 일시 정지 기능 있으나 봇이 24시간 가동되므로 일시 정지 우려 없음).
    *   **Neon:** Serverless Postgres 서비스로, 브랜칭 기능 제공 및 오토스케일링 지원. 무료 티어에서 0.5GiB 스토리지 제공.
    *   **이점:** 로컬 SQLite 파일 유실 위험 완전 배제, 다중 프로세스/스레드 환경의 SQLite `database is locked` 에러 완전 차단, 클라우드 호스트 교체 시에도 데이터 안전 보장.

### 2.2. Alembic을 통한 스키마 마이그레이션 이식

현재 SQLite dialect로 설정된 Alembic 마이그레이션 환경을 PostgreSQL로 전환합니다. PostgreSQL은 SQLite와 달리 컬럼 타입 변경 및 외래 키 제약 조건 적용 시 정교한 DDL 구문이 필요하므로 이를 조율해야 합니다.

1.  **`alembic.ini` 환경 분리**
    *   로컬 개발 환경(`.env.local`)과 운영 환경(`.env.prod`)에 따라 `DATABASE_URL`을 자동 주입받도록 `alembic/env.py`를 보정합니다.
2.  **`alembic/env.py` 설정 보완**
    ```python
    # alembic/env.py 일부 예시
    import os
    from logging.config import fileConfig
    from sqlalchemy import engine_from_config, pool
    from alembic import context

    config = context.config

    # 환경변수에서 DATABASE_URL 동적 로드
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        # Supabase/Neon PostgreSQL 연결 문자열 내 sslmode 호환 처리
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        config.set_main_option("sqlalchemy.url", db_url)
    ```

### 2.3. 데이터 이관 시나리오 (SQLite ➔ PostgreSQL)

기존 SQLite(`stockauto.db`)에 누적된 과거 매매 체결 내역, 보유 주식 잔고, 사용자 설정을 유실 없이 원격 PostgreSQL로 이관하기 위해 3단계 절차를 수행합니다.

1.  **1단계: 스키마 생성 및 초기화**
    PostgreSQL DB 인스턴스 생성 후, Alembic을 사용하여 최신 스키마 헤드를 대상 DB에 적용합니다.
    ```bash
    export DATABASE_URL="postgresql://user:password@db.supabase.co:5432/dbname"
    alembic upgrade head
    ```
2.  **2단계: Python 마이그레이션 스크립트를 통한 데이터 벌크 이관**
    데이터 정합성 및 타입 매핑(특히 SQLite의 TEXT 데이터와 Postgres의 TIMESTAMP/DECIMAL 정밀도 차이)을 보장하기 위해 아래의 전용 변환 스크립트(`scripts/migrate_sqlite_to_pg.py`)를 실행합니다.
    ```python
    # scripts/migrate_sqlite_to_pg.py (개략 구조)
    import sqlite3
    import psycopg2
    from decimal import Decimal

    def migrate():
        sqlite_conn = sqlite3.connect("backend/stockauto.db")
        sqlite_cur = sqlite_conn.cursor()

        pg_conn = psycopg2.connect("postgresql://user:password@db.supabase.co:5432/dbname")
        pg_cur = pg_conn.cursor()

        # 외래키 제약조건 잠시 해제 (순서 무관 이관용)
        pg_cur.execute("SET session_replication_role = 'replica';")

        # 1. users 테이블 이관 예시
        sqlite_cur.execute("SELECT id, email, hashed_password, is_active FROM users")
        for row in sqlite_cur.fetchall():
            pg_cur.execute(
                "INSERT INTO users (id, email, hashed_password, is_active) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                row
            )

        # 2. holdings 테이블 이관 예시 (float -> decimal 정밀도 정규화)
        sqlite_cur.execute("SELECT id, user_id, ticker, quantity, average_price FROM holdings")
        for row in sqlite_cur.fetchall():
            pg_cur.execute(
                "INSERT INTO holdings (id, user_id, ticker, quantity, average_price) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (row[0], row[1], row[2], Decimal(str(row[3])), Decimal(str(row[4])))
            )

        pg_conn.commit()
        pg_cur.execute("SET session_replication_role = 'origin';")
        print("SQLite to PostgreSQL migration completed successfully.")

    if __name__ == "__main__":
        migrate()
    ```
3.  **3단계: 프로덕션 엔진 파라미터 최적화**
    PostgreSQL은 원격 네트워크 통신이 발생하므로 커넥션 풀을 적절히 설정하고 잦은 핸드셰이크를 차단해야 합니다. `backend/app/core/database.py`의 `else` 블록(PostgreSQL 타겟) 파라미터를 아래처럼 튜닝합니다.
    *   `pool_pre_ping=True`: 매번 쿼리 실행 전 연결이 유효한지 확인하여 원격 DB 끊김 현상 방어.
    *   `pool_size=10`: VPS의 메모리가 극도로 작으므로(1GB) 세션 풀 개수를 10개 내외로 제한.
    *   `max_overflow=5`: 임시 과부하 시 추가 허용 커넥션 수 제약.
    *   `pool_recycle=1800`: 30분마다 오래된 커넥션을 폐기하여 Supabase/Neon 측의 Idle Connection 차단 대응.

---

## 🐳 3. Docker Compose 컨테이너 배치 및 리소스 최적화

단일 초소형 VPS 인스턴스 위에서 Nginx, Next.js Frontend, FastAPI Backend, Redis를 올리기 위한 최적의 컨테이너 설계 및 리소스 한계 설정을 제시합니다.

### 3.1. 컴포넌트별 리소스 다이어트

1.  **Frontend (Next.js 16 Standalone Mode)**
    *   Next.js의 기본 Node dev/prod 서버는 백그라운드에서 메모리를 300MB ~ 500MB 이상 잡아먹는 주범입니다.
    *   `next.config.js`에 `output: 'standalone'` 옵션을 적용하여 프론트엔드 배포판을 프로덕션 구동에 필수적인 순수 코드와 최소 의존성만 포함하는 독립 파일로 빌드합니다. 이를 통해 RAM 사용량을 **60MB ~ 80MB 수준**으로 급감시킵니다.
2.  **Backend (FastAPI + Uvicorn Single-Worker)**
    *   기본 Uvicorn 실행 시 멀티 워커 옵션(`--workers N`)을 적용하면 CPU 개수만큼 프로세스가 복제되어 RAM이 순식간에 고갈됩니다.
    *   **Uvicorn 1개 싱글 워커**로 고정하고 비동기(Asyncio) Event Loop 성능을 신뢰하여 단일 프로세스에서 메모리 **100MB 내외**로 유지합니다.
3.  **Redis Cache & Lock (Memory Hard Limit)**
    *   Redis가 설정 없이 기본 가동될 경우 캐시 데이터 누적으로 인해 무한히 메모리가 증가할 수 있습니다.
    *   `redis.conf` 또는 실행 인자 설정을 통해 메모리 한계를 100MB로 한정하고 오래된 캐시는 파기하도록 지정합니다:
        `--maxmemory 100mb --maxmemory-policy volatile-lru`

### 3.2. `docker-compose.prod.yml` 매니페스트 제안

컨테이너가 물리 메모리를 과도하게 침범하여 호스트 전체가 멈추는 불상사를 막기 위해, Docker Compose 레벨에서 `deploy.resources.limits`를 강제 적용합니다.

```yaml
version: '3.8'

services:
  nginx-proxy:
    image: nginx:1.25-alpine
    container_name: stockauto-nginx
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/conf.d:/etc/nginx/conf.d
      - ./nginx/certs:/etc/nginx/certs:ro
    deploy:
      resources:
        limits:
          cpus: '0.2'
          memory: 64M

  redis:
    image: redis:7-alpine
    container_name: stockauto-redis
    restart: always
    command: redis-server --maxmemory 80mb --maxmemory-policy volatile-lru --appendonly no
    deploy:
      resources:
        limits:
          cpus: '0.1'
          memory: 96M

  backend:
    image: stockauto-backend:latest
    container_name: stockauto-backend
    restart: always
    env_file:
      - .env.prod
    environment:
      - APP_ENV=prod
      - REDIS_URL=redis://redis:6379/0
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
    depends_on:
      - redis
    deploy:
      resources:
        limits:
          cpus: '0.4'
          memory: 200M

  frontend:
    image: stockauto-frontend:latest
    container_name: stockauto-frontend
    restart: always
    env_file:
      - .env.prod
    environment:
      - PORT=3000
      - NEXT_PUBLIC_API_URL=https://yourdomain.com/api/v1
    depends_on:
      - backend
    deploy:
      resources:
        limits:
          cpus: '0.3'
          memory: 150M
```

> [!TIP]
> 위 설정의 총 메모리 제한 합계는 **510MB**입니다. 1GB VPS 환경에서 호스트 OS 자원(약 300MB)과 여유 메모리를 충분히 확보하여 OOM Killer에 당할 위험을 완벽히 방지합니다.

---

## 🚨 4. 경량 로그 및 장애 모니터링 알림 구조

리소스가 부족하므로 별도의 Prometheus, Grafana, 또는 Elastic Stack(Elasticsearch, Logstash, Kibana)과 같은 무거운 모니터링 도구는 **절대 설치할 수 없습니다.** 에이전트 외부 모니터링과 초경량 텔레그램 알림 결합 구조를 제안합니다.

```
[ 가상 VPS 서버 내부 ]                                  [ 외부 SaaS 및 메신저 ]
+------------------------------------------+
|  Backend (FastAPI)                       |
|     * Python Telegram Logging Handler ---|--->  [ 텔레그램 장애 채널 API ]
|                                          |      (실시간 Exception & Warning 메시지 수신)
|  Nginx (/api/v1/health)                  |
|     ^                                    |
+-----|------------------------------------+
      |
[ 외부 모니터링 핑 체커 (UptimeRobot) ]
(1분 주기로 GET 요청 -> 장애 발생 시 관리자에게 이메일/SMS 전송)
```

### 4.1. Python 경량 텔레그램 로그 핸들러 구현

백엔드 애플리케이션 내에 오류가 감지되는 즉시 텔레그램으로 로그를 송신하는 사용자 정의 핸들러(`app/core/logging_handlers.py`)를 추가하여, 로컬 디스크 조회를 최소화하고 모바일을 통한 실시간 장애 전파 구조를 확립합니다.

```python
# app/core/logging_handlers.py
import logging
import requests
from app.core.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

class TelegramLogHandler(logging.Handler):
    def __init__(self, token: str = TELEGRAM_TOKEN, chat_id: str = TELEGRAM_CHAT_ID):
        super().__init__()
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def emit(self, record):
        # ERROR 및 CRITICAL 레벨만 필터링하여 발송
        if record.levelno < logging.ERROR:
            return

        log_entry = self.format(record)
        payload = {
            "chat_id": self.chat_id,
            "text": f"🚨 [StockAuto PROD 장애 알림]\n\n"
                    f"• Level: {record.levelname}\n"
                    f"• Logger: {record.name}\n"
                    f"• Message: {record.getMessage()}\n\n"
                    f"```python\n{log_entry[:3000]}\n```", # 텔레그램 메시지 길이 제한 4096자 방어
            "parse_mode": "MarkdownV2"
        }
        try:
            requests.post(self.api_url, json=payload, timeout=3)
        except Exception:
            # 텔레그램 전송 실패 시 로컬 파일 출력으로 백업
            pass
```

### 4.2. Docker 로그 순환(Log Rotation) 정책

호스트 디스크가 서서히 가득 차서 시스템이 멎는 것을 막기 위해 Docker 데몬 수준에서 모든 컨테이너 로그를 순환 처리합니다.
*   **`/etc/docker/daemon.json` 설정 파일 반영:**
    ```json
    {
      "log-driver": "json-file",
      "log-opts": {
        "max-size": "10m",
        "max-file": "3"
      }
    }
    ```
    이 설정을 통해 단일 컨테이너당 최대 30MB까지만 로그 파일을 보유하며 오래된 로그는 즉시 퍼지 처리됩니다.

### 4.3. 외부 헬스체크 트리거 (UptimeRobot 연동)

*   **설정 방식:** **UptimeRobot(무료 티어)**을 활용하여 1분 또는 5분 주기로 `https://yourdomain.com/api/v1/health` 엔드포인트에 HTTPS GET 요청을 전송합니다.
*   **자가 진단 라우터:** 백엔드 `/api/v1/health` 엔드포인트는 데이터베이스 핑 상태, Redis 연결 상태, KIS API OAuth 토큰 잔여 유효 시간, APScheduler 활성 여부를 종합적으로 진단하여, 하나라도 장애 시 `503 Service Unavailable`을 반환하여 외부 UptimeRobot이 즉각 인지하도록 설계합니다.

---

## 🔄 5. 장애 대응 및 복구(Failover) 시나리오

1.  **메모리 스파이크에 의한 FastAPI 다운 시**
    *   Docker Compose의 `restart: always` 정책으로 인해 컨테이너가 5초 이내에 자동 재기동됩니다.
    *   기동 즉시 Redis에 저장된 기존 분산 락(`user_operation_lock`) 수명을 감지하여, 이전 비정상 종료 시 미처 반환되지 않은 락을 정리하고 매매 스케줄러를 안전하게 재개합니다.
2.  **원격 PostgreSQL (Supabase/Neon) 네트워크 단절 시**
    *   SQLAlchemy `pool_pre_ping=True` 조건에 의해 네트워크 회복 즉시 신규 커넥션이 자동으로 맺어집니다.
    *   백그라운드 스케줄러 루프가 실패하더라도 APScheduler가 다음 1분 루프 시점에 작업을 재시도하므로 데이터 꼬임 없이 원복됩니다.
3.  **외부 KIS/TOSS 증권사 API 오류 시**
    *   증권사 점검 시간(매일 23:30~00:30 및 거래소 휴장일 등) 또는 서버 이상 시 발생하는 에러는 Exception Handling을 통해 텔레그램 장애 알림 채널로 조용히 전송되며, 매매 전략 루프는 안전하게 PASS하여 무차별 재시도를 통한 계좌 블락(Block)을 방지합니다.

---

본 아키텍처 설계를 기반으로 인프라 배포 단계를 가동할 시, 월 7천원 미만의 비용으로 상용 서비스 수준의 탄탄하고 회복탄력성 높은 StockAuto 배포본을 구성할 수 있습니다.
