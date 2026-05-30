# StockAuto API 응답 및 에러 표준 규격

본 문서는 백엔드(FastAPI)와 프런트엔드(Next.js) 간의 통신 규격을 정의합니다. 모든 API 응답은 아래 형식을 엄격히 준수합니다.

---

## 1. 성공 응답 (Success Response)
HTTP 상태 코드: `200 OK`

성공 시에는 항상 `SUCCESS` 코드와 함께 실제 결과 데이터를 `data` 필드에 담아 반환합니다.

```json
{
    "code": "SUCCESS",
    "message": "요청이 성공적으로 처리되었습니다.",
    "data": { 
        "total_asset": 15420000,
        "cash_balance": 4500000
    }
}
```

## 2. 에러 응답 (Error Response)
HTTP 상태 코드: `4xx` 또는 `5xx`

에러 발생 시에는 최상위 `error` 객체 안에 상세 정보를 담아 반환합니다.

```json
{
    "error": {
        "code": "API_KEY_MISSING",
        "message": "KIS API 키 또는 계좌번호가 설정되지 않았습니다."
    }
}
```

### 주요 에러 코드 (Error Codes)
| 코드 | 설명 | 비고 |
| :--- | :--- | :--- |
| `API_KEY_MISSING` | .env 파일에 KIS API 정보가 누락됨 | 계좌 조회 시 발생 |
| `SCHEDULER_NOT_READY` | 배경 엔진이 아직 시작되지 않음 | 서버 시작 직후 발생 가능 |
| `WATCHLIST_DUPLICATE` | 이미 관심종목에 등록된 티커 | 등록 요청 시 발생 |
| `SCANNER_ERROR` | 마켓 스캔 엔진 내부 오류 | 500 에러 |

---

## 3. 프런트엔드 처리 가이드
- **Axios Interceptor**: `frontend/lib/api.ts`에 정의된 인터셉터가 성공 시 자동으로 `data`를 추출하므로, 컴포넌트에서는 `res.data`를 통해 실제 데이터에 즉시 접근할 수 있습니다.
- **에러 핸들링**: 에러 발생 시 인터셉터가 `error.message`에 백엔드의 `message` 값을 주입하므로, `error.message`를 그대로 UI에 출력하면 됩니다.
