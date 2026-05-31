# 👑 StockAuto AI & Human Master Directive (CLAUDE.md)

본 문서는 **StockAuto** 프로젝트를 진행하는 모든 AI 어시스턴트(Antigravity)와 인간 개발자가 준수해야 하는 **최상위 절대 수칙이자 단일 백업 가이드 원장**입니다. 

에이전트의 스킬 디렉티브(`SKILL.md`)와 100% 동일하게 동기화되어 있으며, 프로젝트 루트에서 전체 규칙을 직관적으로 확인하고 안전하게 보존 관리하는 유일한 SSOT(Single Source of Truth) 백업본 역할을 합니다.

---

## 🧭 1. AI 핵심 기동 및 검증 프로토콜 (Elite Start & Check)

*   **무추측 개발 원칙 (Zero-Speculation Rule):** 
    *   에이전트는 절대 기존 소스코드의 함수명, 클래스 인터페이스, 데이터베이스 테이블 구조를 '추측'하거나 임의로 가정해서 코드를 작성해서는 안 됩니다.
    *   반드시 변경 대상 소스파일을 `view_file`로 직접 정독하여 실제 임포트 구조와 타입 정의를 눈으로 확인한 뒤 코딩을 시작해야 합니다.
*   **하드 하네스 사전 검증 (Pre-flight Verification):** 
    *   구현이 끝난 후 유저에게 완료 보고를 하기 전에, **반드시 아래 검증 단계를 수행하여 오류가 0건**임을 입증해야 합니다.
    *   **백엔드**: `python -m py_compile [수정한 파일 경로]` 실행 ➔ 문법적 무결성 검증
    *   **프론트엔드**: `npm run lint` 및 `npx tsc --noEmit` 실행 ➔ TypeScript 및 ESLint 에러 0건 검증
*   **완성형 한글 표준화 (NFC Encoding):**
    *   윈도우 환경 및 다양한 OS 간의 한글 깨짐(자소 분리 현상)을 방지하기 위해, 모든 마크다운과 파이썬 소스코드 내 한글 텍스트는 무조건 **완성형(NFC)** 표준으로 디스크에 저장 및 인코딩되어야 합니다.

---

## 🚫 2. Git 명령어 동결 및 시점 통제 (Absolute Git Freeze)

*   **자율 실행 절대 금지:** AI는 개발 진행 중 `git status`, `git add`, `git commit`, `git push`, `git checkout` 등 **그 어떠한 Git 명령어도 자율적으로 실행해서는 안 됩니다 (조회용 status 포함).**
*   **명시적 트리거 활성화:** Git 명령을 통한 진단 및 커밋은 오직 유저가 직접 **"커밋하자"** 혹은 **"깃에 올리자"**라고 한국어 음성/명령 신호를 주었을 때만 한시적으로 허용됩니다.
*   **한글 커밋 메시지 표준:** 모든 커밋 메시지는 유저가 변경 사항을 직관적으로 검증할 수 있도록 구체적인 한글(Korean) 표준을 준수하여 상세히 기술합니다. (예: `feat: KIS API 잔고 환율 연산 정밀화 및 이중 임포트 제거`)

---

## 📋 3. 일자별 현황판 관리 (Daily Task SSOT)

*   **일자별 현황판 기동 (`YYYY-MM-DD.md`):** 
    *   모든 개발 목표와 실시간 작업 목록은 프로젝트 내 **`docs/tasks/`** 폴더 하위에 **당일 날짜 기준의 마크다운 파일(예: `2026-05-31.md`)로 신규 생성 및 분할 적재**되어야 합니다.
    *   절대 프로젝트 루트나 `docs/` 바로 밑에 단일 마스터 `task.md`를 덮어쓰거나 무단 생성하지 않습니다.
*   **작업 선등록 및 승인 프로세스:**
    *   유저와 신규 작업 범위가 합의되는 즉시, 코딩을 시작하기 전에 **당일 기준 일자별 `YYYY-MM-DD.md` 파일에 미완료 `[ ]` 상태로 태스크를 선등록**해야 합니다. 선등록 없는 코딩은 금지됩니다.
    *   코딩 중인 상태는 `[/]`(진행 중)로 표기하며, **유저의 최종 승인(Accept) 사인이 떨어졌을 때만 완료 배지 `[x]`로 갱신**합니다. 리젝 시에는 즉각 상태를 롤백합니다.

---

## 🏛 4. 백엔드 아키텍처 및 상세 표준 (Backend Architecture)

*   **도메인 격리 및 단일 책임 원칙 (SRP):**
    *   모든 비즈니스 로직은 `backend/app/` 아래 도메인 폴더로 격리 관리합니다:
        *   `app/watchlist/` (관심종목 및 필터)
        *   `app/scanner/` (마켓 스캐너 및 AI 뉴스 분석)
        *   `app/bot/` (자동 매매 스케줄러 및 멀티 전략 관리)
        *   `app/trades/` (체결 확인 및 계좌/주문 API)
        *   `app/translations/` (다국어 사전 캐시)
*   **SSOT 코어 모듈 집중:** 
    *   데이터베이스 모델(`models.py`), 연결 세션(`database.py`), 전역 예외(`exceptions.py`), 환경 설정(`config.py`)은 무조건 **`app/core/` 하위 폴더**로 단일화합니다.
    *   순환 참조(Circular Imports)를 차단하기 위해 임포트 시 절대 경로 (`from app.core...`)로 통일하고 필요시 지연 임포트(Lazy Import)를 사용합니다.
*   **Alembic 마이그레이션 필수 준수:**
    *   DB 스키마 컬럼 변경 시, 소스코드 내에 임시 ALTER TABLE SQL을 주입하는 꼼수를 엄격히 금지합니다. 무조건 `models.py` 수정 후 `alembic`을 통해 마이그레이션 스크립트를 작성하며, 앱 구동 시 `migrator.py`가 자동으로 이를 감지하여 안전하게 실행(기존 DB는 Stamp, 신규 DB는 Upgrade)하도록 관리합니다.

---

## 💻 5. 프론트엔드 및 고성능 UI 표준 (Frontend & UI)

*   **기술 스택:** Next.js 15 (App Router), Vanilla CSS, Lucide React, Premium HSL 다크 모드 테마.
*   **프레임워크 표준 엄격 준수 (No Hacks):**
    *   린트 에러를 임시방편으로 모면하기 위한 우회 기술(예: `any` 캐스팅, `setTimeout` 난사, 무작정 eslint-disable 적용)을 절대 금지합니다. React 18+의 렌더링 최적화, 비동기 데이터 패칭 가이드라인 등 프레임워크가 권장하는 **'정석(Standard)' 패턴**으로 정밀 구현합니다.
*   **Vue 마스터용 React 트러블슈팅 문서화:**
    *   개발 중 신규 React Hook을 채택하거나 컴포넌트 렌더링 최적화 트러블슈팅이 완료되면, 반드시 그 즉시 **`docs/REACT_GUIDE.md`** 가이드 문서를 직관적인 비유와 함께 현행화하여 기록을 보존해야 합니다.

---

## ⚙️ 6. 런타임 퀵 레퍼런스 (CLI Quick Commands)

### 1. 백엔드 가동 모드 선택
```bash
# In backend/ folder
python run.py local  # 가상 simulated 투자 환경 기동
python run.py dev    # 모의투자(MOCK) 금융 서버 연동 기동
python run.py prod   # 실전투자(REAL) 라이브 정규 트레이딩 기동
```

### 2. Alembic 마이그레이션 도구
```bash
alembic revision --autogenerate -m "스키마설명"
alembic upgrade head
```

### 3. 프론트엔드 빌드 및 분석
```bash
# In frontend/ folder
npm run dev     # 개발 로컬 서버 구동
npm run build   # 프로덕션 빌드 무결성 확인
npm run lint    # ESLint 정적 분석 통과 검증
```
