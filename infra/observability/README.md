# 관측 스택 (Prometheus + Alertmanager + redis_exporter + Grafana)

Redis가 죽으면 **텔레그램으로 알림**을 보내기 위한 로컬 관측 스택이다.
제품 코드와 완전히 분리돼 있으며, 백엔드는 이 스택의 존재를 모른다.

왜 필요한가: 주문 락이 Redis에 있어서 Redis가 죽으면 신규 주문이 fail-closed로 전량
차단된다(`app/core/locks.py`). 그런데 지금 이 상태를 알 수 있는 경로는 관리자가 직접
`/admin/system` 화면을 열었을 때뿐이고, 그 화면조차 기본 갱신 주기가 수동이다.
무인 자동매매에서 이건 사각지대다.

> ⚠️ **상시 구동 전제가 아니다.** 이 스택은 백엔드와 같은 PC에서 돌기 때문에 PC 자체가
> 죽으면 감시자도 함께 죽는다. 그 한계는 아래 "한계" 절 참조.

---

## 1. 사전 준비 (최초 1회)

### 1-1. Docker Desktop

WSL2가 없으면 Docker Desktop 설치 과정에서 함께 설치된다.

**설치 경로와 디스크 이미지 위치는 기본값(`C:`) 그대로 둔다.** 이 스택의 이미지는 다 합쳐
700MB 남짓이고 WSL2 디스크 이미지도 3~5GB선에서 안정되므로, 기본 위치로 충분하다.
오히려 `D:`로 옮기면 프로젝트(`backend/data`의 파케이 캐시 약 6.8GB, `node_modules`
3만여 파일)와 **같은 5400rpm HDD의 헤드를 나눠 쓰게 되어** 백테스트·프론트 빌드와
탐색 경합이 생긴다. `C:`는 NVMe SSD라 그 경합이 없다.

대신 아래 **(a) 메모리 상한은 반드시 건다.** 이 PC의 실제 제약은 디스크가 아니라 메모리다.

**(a) WSL2 메모리 상한을 건다**

`%UserProfile%\.wslconfig` 파일을 만들고:

```ini
[wsl2]
memory=3GB
processors=4
```

상한을 걸지 않으면 WSL2가 전체 메모리의 절반까지 잡는다. 프론트 dev 서버와 백엔드가
같이 떠 있는 상태에서는 그대로 스왑 구간에 들어간다. 수정 후 `wsl --shutdown` 으로 반영.

**(b) 공간이 조여오면 그때 옮긴다**

`ext4.vhdx`는 한번 커지면 컨테이너를 지워도 자동으로 줄지 않는다. 주기적으로 확인한다.

```bash
docker system df
```

`C:` 여유가 10GB 아래로 내려가면 `docker system prune` 으로 정리하거나,
`Settings → Resources → Advanced → Disk image location` 에서 `D:\docker-data` 등으로
옮긴다. 이동은 나중에도 몇 번의 클릭이면 되므로 미리 옮겨둘 이유가 없다.
옮기면 위에서 말한 HDD 헤드 경합을 감수하게 된다는 점만 알고 결정할 것.

### 1-2. 텔레그램 봇 토큰

`alertmanager/secrets/telegram_token` 파일에 토큰을 **한 줄로만** 넣는다.

```bash
echo "123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxx" > infra/observability/alertmanager/secrets/telegram_token
```

`backend/.env`의 `TELEGRAM_BOT_TOKEN`과 같은 봇을 써도 되고, 운영 알림 전용 봇을 새로
파도 된다. 토큰을 `alertmanager.yml`에 직접 적지 말 것 — 설정 파일 내용은 Alertmanager의
상태 API에 노출될 수 있고, `bot_token_file`은 그 경로를 피하려고 쓰는 것이다.

### 1-3. chat_id 확인

알림을 받을 대화방에서 봇에게 아무 메시지나 한 번 보낸 뒤:

```bash
curl -s "https://api.telegram.org/bot<토큰>/getUpdates"
```

응답의 `result[].message.chat.id`가 chat_id다. **개인 DM은 양수, 그룹·채널은 `-100`으로
시작하는 음수**다. 봇을 그룹에 넣었다면 그룹에서 메시지를 보내야 그 방의 id가 잡힌다.

### 1-4. Alertmanager 설정 파일 생성

```bash
cp infra/observability/alertmanager/alertmanager.yml.example infra/observability/alertmanager/alertmanager.yml
```

복사한 파일에서 `chat_id: 0` 을 실제 값으로 바꾼다.
**따옴표를 씌우면 안 된다.** 정수여야 하고, 문자열이면 설정 로딩 자체가 실패한다.
이 파일은 `.gitignore`로 제외된다(Alertmanager는 환경변수 치환을 지원하지 않아 환경별
값을 파일에 직접 적어야 하기 때문).

---

## 2. 기동 / 중지

```bash
docker compose -f infra/observability/docker-compose.yml up -d
```

메모리를 아끼려면 Grafana를 빼도 된다. 학습·알림 목적에는 Prometheus 내장 UI로 충분하다.

```bash
docker compose -f infra/observability/docker-compose.yml up -d prometheus alertmanager redis-exporter
```

```bash
docker compose -f infra/observability/docker-compose.yml down
```

| 주소 | 용도 |
| :--- | :--- |
| http://localhost:9090/targets | 스크레이프 대상 상태 |
| http://localhost:9090/alerts | 알림 규칙 상태 (Inactive / Pending / Firing) |
| http://localhost:9093 | Alertmanager — 발화 중 알림, 무음 처리 |
| http://localhost:3001 | Grafana (admin / admin) |

모든 포트는 `127.0.0.1`에만 바인딩된다. Prometheus UI에는 인증이 없으므로 외부에 열지 말 것.

---

## 3. 실제로 되는지 확인

설정만 맞춰놓고 "잘 되겠지" 하면 정작 장애 때 알림이 안 온다. 반드시 한 번은 죽여본다.

**1) 대상이 붙었는지**

http://localhost:9090/targets 에서 `redis` 잡이 **UP**인지 확인.
DOWN이면 Memurai가 안 떠 있거나(`start_dev.bat`이 자동 기동한다) `host.docker.internal`
해석이 안 되는 경우다.

**2) 지표가 나오는지**

http://localhost:9090 의 쿼리 창에 `redis_up` 을 넣고 값이 `1`인지 본다.

**3) 장애를 주입한다 (실제 Redis는 건드리지 않는다)**

> ⚠️ **Memurai를 죽여서 시험하지 말 것.** 백엔드가 떠 있는 동안 Redis가 사라지면 그 시간
> 동안 신규 주문이 fail-closed로 전량 차단된다. 장중이면 실제 매매 기회를 잃는다.
> 아래 오버레이는 exporter가 바라보는 주소만 죽은 포트로 바꾼다. Prometheus 입장에서는
> 진짜 장애와 완전히 동일한 `redis_up == 0`이 되지만 Redis 자체는 멀쩡하다.

```bash
docker compose -f infra/observability/docker-compose.yml -f infra/observability/docker-compose.faultdrill.yml up -d redis-exporter
```

- 즉시: `redis_up`이 0
- 약 2분 뒤: http://localhost:9090/alerts 의 `RedisDown`이 **Pending → Firing**
- Firing 후 최대 30초(`group_wait`) 안에 **텔레그램 알림 도착**

**4) 원상 복구한다**

```bash
docker compose -f infra/observability/docker-compose.yml up -d redis-exporter
```

오버레이를 빼고 다시 올리면 컨테이너가 원래 주소로 재생성된다.
복구되면 `send_resolved: true` 에 의해 **해소 알림**이 온다.

> 📌 **해소 알림은 바로 오지 않는다.** `group_interval: 5m` 때문에 마지막 발송으로부터
> 5분이 지난 뒤에야 나간다. 실측에서도 `redis_up`이 1로 돌아오고 규칙이 `inactive`가 된
> 뒤 약 4분 30초가 더 지나서 도착했다. 알림이 안 온다고 오판하지 말 것 —
> `alertmanager_notifications_total{integration="telegram"}` 카운터로 확인하는 편이 정확하다.

**실측 타임라인** (2026-09-01 검증):

| 경과 | 상태 |
| :--- | :--- |
| 0s | 장애 주입 → `redis_up` 0으로 즉시 전환 |
| ~20s~120s | `RedisDown` **pending** (`for: 2m` 대기) |
| ~140s | **firing** 전환 |
| ~160s | **텔레그램 발화 알림 도착** (실패 0건) |
| 복구 +15s | `redis_up` 1, 규칙 `inactive` |
| 복구 +약 4분 30초 | **텔레그램 해소 알림 도착** |

알림이 안 오면 Alertmanager 로그를 본다. 대부분 chat_id 오타나 토큰 문제다.

```bash
docker compose -f infra/observability/docker-compose.yml logs alertmanager
```

**5) 점검 중 알림 끄기**

```bash
docker exec stockauto-alertmanager amtool --alertmanager.url=http://localhost:9093 silence add alertname=RedisDown --duration=2h --comment="계획된 점검"
```

---

## 4. 알림 규칙

`prometheus/rules/redis.yml`

| 알림 | 조건 | 지속 | 등급 |
| :--- | :--- | :--- | :--- |
| `RedisDown` | `redis_up == 0` | 2m | critical |
| `RedisExporterDown` | `up{job="redis"} == 0` | 3m | warning |
| `RedisRestarted` | uptime < 5분 | 1m | warning |
| `RedisMemoryPressure` | 사용량 > maxmemory 90% | 5m | warning |
| `RedisRejectedConnections` | 5분간 거부 발생 | 1m | warning |
| `Watchdog` | 항상 | — | (외부 데드맨용) |

`RedisRestarted`가 중요하다. Redis가 조용히 재시작하면 **주문 락이 전부 사라진다**.
로컬 Memurai는 `--save "" --appendonly no`로 뜨므로 재시작 시 키가 남지 않는다.

`for` / `repeat_interval` 값을 바꿔가며 알림이 어떻게 억제되는지 보는 게 이 스택의
학습 포인트다. 직접 구현하면 이 동작들(지속시간 확인, 중복 제거, 재통보 주기, 복구 통보,
억제 규칙)을 전부 손으로 짜야 한다.

---

## 5. 자원 사용량

아래는 추정이 아니라 이 PC에서 `docker stats`로 **실측한 값**이다 (2026-09-01, 스택 기동
직후 유휴 상태).

| 구성요소 | 메모리 | CPU |
| :--- | ---: | ---: |
| Grafana | 70 MB | 1.5% |
| Prometheus | 31 MB | 0.0% |
| Alertmanager | 18 MB | 0.1% |
| redis_exporter | 8 MB | 0.0% |
| **컨테이너 소계** | **~128 MB** | ~1.6% |
| vmmemWSL (상한 3GB) | 3,055 MB | — |
| Docker Desktop 프로세스 | 788 MB | — |
| **실질 총계** | **~3.8 GB** | |

**컨테이너는 예상보다 훨씬 가볍고(128MB), 무거운 건 전적으로 Docker Desktop 런타임이다.**
그래서 `.wslconfig` 메모리 상한이 설치 위치보다 중요하다. 상한을 3GB로 걸어둔 상태에서
`vmmemWSL`이 정확히 그 값까지 차오르는 것을 확인했다 — 상한이 없었다면 8GB까지 갔다.

스택 기동 후 호스트 메모리 사용률은 85%(여유 2.4GB)였다. 백엔드·프론트 dev 서버와
공존은 되지만 여유가 크지는 않으므로, 무거운 백테스트나 E2E를 돌릴 때는 스택을 내리는 편이 낫다.

디스크는 이미지 4종 합계 **1.25GB**, 볼륨(TSDB 포함) 25MB로 실측됐다.
CPU는 유휴 시 사실상 0이다.

---

## 6. 한계 (알고 쓸 것)

- **자기 자신은 감시하지 못한다.** Prometheus가 백엔드와 같은 PC에 있어서 정전이나 PC
  다운이면 감시자도 같이 죽는다. `Watchdog` 규칙은 이를 위해 넣어 뒀지만, 외부 데드맨
  스위치(Healthchecks.io 등) 연결은 아직 하지 않았다. 지금은 null 수신자로 흘려보낸다.
- **백엔드 내부 상태는 안 보인다.** redis_exporter는 Redis만 본다. 락 임대 상실
  (`CRITICAL_LOST`), 레이트리미터 폴백 전환, SSE publish 실패, 매매 루프 stall은
  백엔드가 `/metrics`를 노출해야 관측된다. `prometheus.yml`에 잡이 주석으로 준비돼 있다.
- **스택이 꺼져 있으면 알림도 없다.** 상시 구동하지 않는다면 감시 공백이 생긴다.
  항상 켜져 있어야 하는 알림이 필요하면 백엔드 인프로세스 워치독이 더 맞는 구조다.
