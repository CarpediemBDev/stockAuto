# 환경별 설정 관리 체계 개선 계획 (Implementation Plan)

본 문서는 기존의 단일 `.env` 설정 방식에서 스프링부트 스타일의 **환경별 설정 분리 체계(`APP_ENV` 기반)**로 전환하는 상세 설계안입니다.

## 1. 개요 및 목적
- **목적**: 개발(모의투자)과 운영(실전매매) 설정을 물리적 파일로 분리하여 보안 사고를 예방하고 관리 편의성을 증대합니다.
- **방식**: `APP_ENV` 환경 변수를 통해 로드할 `.env` 파일을 결정하는 전략을 사용합니다.

## 2. 상세 변경 사항

### A. 백엔드 설정 로직 (`backend/config.py`)
- `APP_ENV` 값(`dev` 또는 `prod`)에 따라 `.env.dev` 또는 `.env.prod`를 선택적으로 로드합니다.
- `Settings` 클래스 내의 변수명을 `KIS_REAL_APP_KEY` 등에서 `KIS_APP_KEY`와 같이 공통 명칭으로 통일합니다.

### B. 설정 템플릿 생성
- **`.env.dev.example`**: 모의투자용 설정 템플릿 (기본 `TRADE_MODE=VIRTUAL`)
- **`.env.prod.example`**: 실전매매용 설정 템플릿 (기본 `TRADE_MODE=REAL`)
- 기존 `.env.example`은 삭제합니다.

### C. 프로젝트 문서 및 인프라
- **`.gitignore`**: `.env.*` 파일을 차단하되 `.env.*.example`은 허용하도록 수정합니다.
- **`README.md` & `SYSTEM_MANUAL.md`**: 새로운 환경 설정 및 실행 방법을 반영하여 업데이트합니다.

## 3. 검증 계획
- `APP_ENV=dev` 실행 시 모의투자 서버 접속 및 로그 확인.
- `APP_ENV=prod` 실행 시 실전매매 서버 접속 및 로그 확인.
- 설정 파일 누락 시의 예외 처리 확인.
