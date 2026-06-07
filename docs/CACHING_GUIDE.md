# 🚀 시스템 캐싱 아키텍처 가이드 (Caching Architecture Guide)

이 문서는 대규모 트래픽을 처리하는 웹 서비스와 **StockAuto** 프로젝트에서 캐시(Cache)를 어떻게 다루고 활용하는지에 대한 기술적 정리본입니다.

---

## 1. 캐시의 종류와 위치 비교

| 종류 | 위치 | 장점 | 단점 | 활용 사례 |
| :--- | :--- | :--- | :--- | :--- |
| **Web Cache** | Nginx, CDN 등 웹 서버 앞단 | 초고속, WAS 부하 원천 차단 | 동적 데이터(댓글 등) 처리 불가 | 변하지 않는 이미지, 정적 소개 페이지 |
| **Local Cache** | WAS 내부 메모리 (FastAPI Dict, Ehcache) | 네트워크 통신 불필요 (가장 빠름), 설정 간편 | WAS 2대 이상(Scale-Out)일 때 **데이터 불일치 발생** | 트래픽이 적은 단일 서버, 개인용 자동매매 봇 |
| **Global Cache** | WAS 외부 별도 서버 (Redis, Memcached) | 여러 대의 WAS가 하나의 캐시를 공유하여 **데이터 완벽 일치** | 별도의 인프라 구축 및 네트워크 통신 비용(ms) 발생 | 네이버, 디시인사이드 등 대형 게시판 서비스 |

> [!NOTE]
> **StockAuto 봇의 캐시 전략 (Local Cache)**
> 우리 봇은 서버 1대에서 혼자 돌아가기 때문에 복잡한 Redis를 쓰지 않고, 파이썬 전역 딕셔너리(`dict`)를 활용한 메모리 로컬 캐싱을 사용합니다. 외부 API(야후 파이낸스)의 IP 차단(Rate Limit)을 막기 위해 10초 ~ 24시간 단위의 **시간 만료형(TTL)** 방식을 채택하고 있습니다.

---

## 2. 대형 게시판의 마법: "캐시 무효화 (Cache Invalidation)"

대형 게시판은 수백만 건의 조회를 DB 부하 없이 처리하기 위해 캐시를 씁니다. 하지만 새 댓글이 달리면 즉각 보여줘야 하므로, 단순히 "10분 유지" 같은 TTL 방식이 아니라 **사건 발생 시 캐시를 파괴하는 이벤트 기반 방식**을 사용합니다.

1. **조회 (GET)**: 캐시에 데이터가 있으면 DB 안 거치고 즉시 반환 (Cache Hit).
2. **작성 (POST)**: 새 댓글이 달리면 DB에 먼저 저장하고, **해당 게시물의 기존 캐시를 즉시 파괴(Delete)**.
3. **다음 조회**: 캐시가 파괴되었으므로 어쩔 수 없이 DB에서 최신 데이터를 가져온 뒤 다시 캐시에 저장 (Cache Miss -> DB Read -> Cache Update).

---

## 3. FastAPI 로컬 메모리 캐시 & 무효화 예제 코드

별도의 외부 인프라 없이 파이썬 로컬 딕셔너리(`{}`)를 이용해 '캐시 무효화' 원리를 구현한 예제입니다.

```python
from fastapi import FastAPI
from pydantic import BaseModel
import time

app = FastAPI()

# 1. WAS 내부 메모리를 캐시 저장소로 사용 (전역 딕셔너리)
_comments_cache = {}

# 임시 가짜 DB
_fake_db = {
    1: ["첫 번째 댓글입니다.", "좋은 글이네요!"]
}

class Comment(BaseModel):
    post_id: int
    content: str

# 🟢 [조회 API] : 게시물 댓글 읽기
@app.get("/posts/{post_id}/comments")
async def get_comments(post_id: int):
    # 1. 캐시 히트(Cache Hit) 확인
    if post_id in _comments_cache:
        print("⚡ 캐시에서 0.001초 만에 가져옵니다!")
        return {"source": "cache", "data": _comments_cache[post_id]}

    # 2. 캐시 미스(Cache Miss): DB에서 무겁게 읽어옴 (가정)
    print("🐢 DB에서 무겁게 읽어옵니다...")
    time.sleep(1) # DB 지연시간 1초 가정
    db_data = _fake_db.get(post_id, [])

    # 3. 읽어온 데이터를 캐시에 저장해 둠 (다음 사람을 위해)
    _comments_cache[post_id] = db_data
    
    return {"source": "database", "data": db_data}


# 🔴 [작성 API] : 새 댓글 달기
@app.post("/posts/comments")
async def add_comment(comment: Comment):
    # 1. 실제 DB에 새 댓글 저장
    if comment.post_id not in _fake_db:
        _fake_db[comment.post_id] = []
    _fake_db[comment.post_id].append(comment.content)
    
    print(f"✅ DB에 새 댓글 저장 완료: {comment.content}")

    # 2. 🔥 핵심: 해당 게시물의 캐시를 폭파(무효화) 시킴!
    # 이렇게 지워놔야, 다음 조회 시 옛날 캐시를 안 보고 최신 DB를 다시 읽어오게 됨
    if comment.post_id in _comments_cache:
        del _comments_cache[comment.post_id]
        print("💥 새 댓글이 달려서 기존 캐시를 파괴했습니다!")

    return {"msg": "댓글이 등록되었습니다."}
```

---

## 4. 로컬 캐시(WAS 메모리)의 치명적 한계: 데이터 불일치

위 FastAPI 예제(혹은 Spring Boot의 Ehcache) 방식은 서버가 1대일 때는 완벽합니다. 하지만 트래픽이 많아져 서버를 2대 이상으로 늘리면(Scale-Out) 심각한 문제가 생깁니다.

1. 유저 A가 1번 서버에서 게시물을 봄 ➔ 1번 서버 캐시에 저장됨.
2. 유저 B가 2번 서버에서 게시물을 봄 ➔ 2번 서버 캐시에 저장됨.
3. 유저 C가 **1번 서버**에서 **새 댓글을 작성함** ➔ 1번 서버의 캐시는 파괴됨 💥
4. 유저 A가 새로고침하여 **2번 서버**로 연결됨 ➔ **2번 서버의 캐시는 아직 살아있으므로 옛날 데이터를 보여줌! (새 댓글 증발 현상)**

**결론:** 서버가 2대 이상일 때는 WAS 내부에 캐시를 두지 않고, 공용으로 사용할 수 있는 전용 캐시 서버(Redis)를 도입해야 합니다.
