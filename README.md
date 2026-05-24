# 🚀 StockAuto: 고성능 마켓 스캐너 및 트레이딩 봇

**StockAuto**는 미국 주식 시장 전체를 실시간으로 전수 조사하여 고수 투자자들의 필터링 전략(Gap, RVOL, Catalyst)을 기반으로 최적의 매수 기회를 포착하는 자동화 트레이딩 시스템입니다.

![Dashboard Preview](https://via.placeholder.com/1200x600?text=StockAuto+Dashboard+Preview)

## ✨ 주요 기능

- **🌐 전 시장 실시간 스캔**: KIS API 및 Yahoo Finance를 활용하여 나스닥/뉴욕 거래소 전 종목 실시간 스캔.
- **🛡️ 전문가 필터 시스템**: 갭 상승, 상대 거래량(RVOL), 신고가 근접, 지수 대비 강세(RS) 등 7단계 검증 알고리즘.
- **🔥 모멘텀 탐지**: 뉴스 및 공시를 실시간 분석하여 주가 상승의 명분(Catalyst)이 있는 종목 우선 선별.
- **📊 멀티 타임프레임 분석**: 15분봉 추세 필터링과 1분봉 정밀 타점 분석의 듀얼 아키텍처.
- **💻 모던 대시보드**: Next.js 15 기반의 프리미엄 다크 모드 UI와 실시간 시그널 시각화.
- **🤖 텔레그램 트레이딩 브릿지**: 텔레그램 봇 API를 활용한 실시간 계좌 상태 조회(`/status`) 및 매매 제어(`/run`, `/stop`).

## 🛠 기술 스택

### 백엔드 (Backend)

- **FastAPI**: 고성능 비동기 API 서버
- **yfinance**: 글로벌 시장 데이터 추출
- **pandas/numpy**: 고성능 기술적 지표 계산
- **SQLite**: 거래 로그 및 관심 종목 관리

### 프론트엔드 (Frontend)

- **Next.js 15 (App Router)**: 최신 웹 아키텍처
- **Tailwind CSS**: 프리미엄 UI 디자인
- **Lucide React**: 벡터 아이콘 시스템

## 🚀 시작하기

### 사전 요구 사항

- Python 3.10+
- Node.js 18+

### 설치 및 실행

1. **저장소 클론**

   ```bash
   git clone https://github.com/your-id/stockAuto.git
   cd stockAuto
   ```

2. **백엔드 설정**

   ```bash
   cd backend
   python -m venv venv
   source venv/Scripts/activate # Windows: venv\Scripts\activate
   pip install -r requirements.txt

   # 설정 파일 생성 (원하는 환경의 템플릿 복사)
   cp .env.local.example .env.local   # 로컬 시뮬레이션 환경용
   cp .env.dev.example .env.dev       # 모의투자 환경용
   cp .env.prod.example .env.prod     # 실전매매 환경용

   # 서버 실행 (가상환경 수동 활성화 생략 가능! run.py가 자동 감지 및 자가 치환 실행)
   python run.py local  # (또는 인자 생략 시 기본값: python run.py)

   # 서버 실행 (개발 모드)
   python run.py dev

   # 서버 실행 (운영 모드)
   python run.py prod
   ```

   > [!TIP]
   > **💡 가상환경 활성화 생략 가이드:**
   > `run.py` 런처는 자체적으로 로컬 가상환경(`venv`)을 감지하여 가상환경 파이썬 프로세스로 자동 전환(자가 치환, Self Re-execution)합니다. 따라서 패키지 설치(`pip install`) 이후에는 따로 `source venv/Scripts/activate`를 실행하지 않고 바로 `python run.py` 명령어로 서버를 간편하게 실행할 수 있습니다.

3. **프론트엔드 설정**

   ```bash
   cd ../frontend
   npm install

   # 설정 파일 생성
   cp .env.example .env.local

   # 서버 실행 (로컬 환경 구동)
   npm run local

   # 서버 실행 (개발 모드)
   npm run dev

   # 서버 실행 (운영 모드)
   npm run prod
   ```

## 🤖 AI 협업 가이드 (AI Collaboration)

본 프로젝트는 AI 코딩 어시스턴트와의 효율적인 협업을 위해 최적화되어 있습니다.

- **`CLAUDE.md`**: AI가 프로젝트 진입 시 최우선으로 읽는 가이드 맵입니다.
- **`docs/RULES.md`**: AI와 개발자 간의 협업 규칙 및 코드 품질 수칙이 정의되어 있습니다.

## 🔒 보안 및 개인정보 보호

본 저장소에는 시스템의 핵심 매매 전략(Filter & Signal Logic) 마크다운 문서는 포함되어 있지 않습니다. 해당 정보는 개발자의 로직 보호를 위해 비공개로 관리됩니다.

## ⚠️ 면책 조항

본 프로그램은 투자 판단을 돕기 위한 보조 도구이며, 모든 투자의 책임은 투자자 본인에게 있습니다.

---

Created by [Your Name]
