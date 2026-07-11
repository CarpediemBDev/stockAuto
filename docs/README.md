# 📚 StockAuto 문서 인덱스 (Docs SSOT Map)

이 파일은 `docs/` 아래 모든 기술 문서의 **단일 주제 소유권(SSOT)**을 매핑합니다.
새 문서를 추가하거나 기존 문서를 대체할 때는 반드시 이 표를 함께 갱신하고, "같은 주제를 두 문서가 소유"하지 않도록 유지합니다.

> 최상위 AI/개발 작업 규칙은 루트 [`AGENTS.md`](../AGENTS.md), 작업 절차는 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)를 단일 기준으로 사용합니다.
> **Claude Code 세션**은 루트 [`CLAUDE.md`](../CLAUDE.md)가 자동 진입점이며, 거기서 `AGENTS.md`로 연결됩니다.

## 🧭 상시 유지 문서 (Living SSOT)

| 문서 | 소유 주제 (이 문서만 이 주제의 정본) |
|---|---|
| [AI_WORKFLOW.md](AI_WORKFLOW.md) | AI 작업 시작·검증·인수인계 절차, 변경 영향 기록 형식 |
| [ARCHITECTURE_V2.md](ARCHITECTURE_V2.md) | 백엔드 동시성/락/Atomic 연산, PostgreSQL 이관 설계 |
| [SCHEMA.md](SCHEMA.md) | DB 테이블·컬럼·관계 스키마 정본 |
| [API_STANDARD.md](API_STANDARD.md) | 전역 응답 래퍼, API 계약 규격 |
| [SCANNER_DATA_FLOW.md](SCANNER_DATA_FLOW.md) | 스캐너 데이터 파이프라인 흐름 |
| [CACHING_GUIDE.md](CACHING_GUIDE.md) | 캐시 경계(공용 vs 개인) 및 갱신 규칙 |
| [SYSTEM_MANUAL.md](SYSTEM_MANUAL.md) | 시스템 전체 운영 매뉴얼 |
| [SYSTEM_SETTINGS.md](SYSTEM_SETTINGS.md) | 런타임 시스템 설정 항목 정본 |
| [REACT_GUIDE.md](REACT_GUIDE.md) | React 19 훅·렌더링 트러블슈팅 |
| [NEXTJS_GUIDE.md](NEXTJS_GUIDE.md) | Next.js 16 브레이킹 체인지 AI 가드레일 |
| [mistake_note.md](mistake_note.md) | 재발 방지용 치명 버그 근본원인/해결 원장 |

## 🎯 전략 문서 (Strategy — 역할 분리)

| 문서 | 소유 주제 |
|---|---|
| [strategy_specification.md](strategy_specification.md) | 전략 **명세 정본** (레짐 스위칭, 11대 대가 기법 통합) |
| [strategy_scorecard.md](strategy_scorecard.md) | 종목 **채점 기준표**와 장세별 시나리오 |
| [strategy_map.md](strategy_map.md) | 전략 ↔ **소스 파일 구현 맵** (추적표) |
| [strategy_architecture.md](strategy_architecture.md) | 전략 패턴 **OOP 아키텍처** (신규 전략 추가 가이드) |
| [FILTER.md](FILTER.md) | 매수 후보 필터(Gap/RVOL/Catalyst) 정의 |
| [SIGNAL.md](SIGNAL.md) | 매도/익절/트레일링 신호 정의 |

## 🚀 운영·배포 문서

| 문서 | 소유 주제 |
|---|---|
| [PRODUCTION_DEPLOYMENT_PLAN.md](PRODUCTION_DEPLOYMENT_PLAN.md) | 운영 배포 절차 |
| [PRODUCTION_DEPLOYMENT_STRATEGY.md](PRODUCTION_DEPLOYMENT_STRATEGY.md) | 운영 배포 전략(인프라·롤아웃) |
| [OFF_MARKET_AUTOMATION_PLAN.md](OFF_MARKET_AUTOMATION_PLAN.md) | 장외시간 자동화 스케줄러 설계 |

## 🧱 계획 문서 묶음 (`docs/plans/`)

| 문서 | 소유 주제 |
|---|---|
| [plans/product_specification.md](plans/product_specification.md) | 제품 사양·요구사항 |
| [plans/project_roadmap.md](plans/project_roadmap.md) | 프로젝트 로드맵·우선순위 |
| [plans/backend_core_stability.md](plans/backend_core_stability.md) | 백엔드 코어 안정성 계획 |
| [plans/backend_data_ai_strategy.md](plans/backend_data_ai_strategy.md) | 데이터·AI 전략 계획 |
| [plans/cloud_infrastructure_architecture.md](plans/cloud_infrastructure_architecture.md) | 클라우드 인프라 아키텍처 |
| [plans/design_guidelines.md](plans/design_guidelines.md) | 프론트 UX/UI 디자인 가이드라인 |

## 🗂️ 진행 중 계획 문서 (Living Plan)

| 문서 | 성격 | 비고 |
|---|---|---|
| [implementation_plan.md](implementation_plan.md) | 구현 계획 | 최근 갱신 중 — 완료 항목은 현황판/코드로 이관 후 정리 |
| [walkthrough.md](walkthrough.md) | 워크스루 메모 | 상시 문서로 승격 or archive 판단 |

## 🕰️ 이력 스냅샷 (`docs/history/`)

> 전략 문서의 과거 버전 스냅샷입니다. 현행 SSOT는 위 '전략 문서' 섹션이며, 아래는 변천 이력 참조용입니다.

- [history/strategy_specification_V1.md](history/strategy_specification_V1.md) · [history/strategy_masterplan_V2.md](history/strategy_masterplan_V2.md) · [history/strategy_tournament_report_V3.md](history/strategy_tournament_report_V3.md) · [history/strategy_refactoring_walkthrough_V4.md](history/strategy_refactoring_walkthrough_V4.md) · [history/strategy_tournament_report_V5.md](history/strategy_tournament_report_V5.md) (예정)


## 📦 보관 문서 (Archived — `docs/archive/`)

> 특정 시점의 계획/감사/리포트 산출물입니다. 이력 참조용으로만 보관하며 상시 SSOT가 아닙니다.

| 문서 | 성격 |
|---|---|
| [archive/BUG_REPORT_2026-06-04.md](archive/BUG_REPORT_2026-06-04.md) | 일자 버그 리포트 (근본원인 원장은 `mistake_note.md`) |
| [archive/TYPESCRIPT_ANY_REPORT.md](archive/TYPESCRIPT_ANY_REPORT.md) | `any` 정리 감사 리포트 |
| [archive/BACKTEST_ARENA_AUDIT.md](archive/BACKTEST_ARENA_AUDIT.md) | 백테스트 아레나 감사 |
| [archive/REPORT_UPDATE_PLAN.md](archive/REPORT_UPDATE_PLAN.md) | 리포트 개선 계획 (반영 완료) |
