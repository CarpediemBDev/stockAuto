# 🟢 Vue 개발자를 위한 React Hooks 직관 비유 사전

> **[NOTE]**
> 이 문서는 Vue 환경에 익숙한 유저님이 React 프로젝트를 다룰 때, 매번 헷갈리는 React Hooks의 본질과 원리를 10초 만에 직관적으로 기억해 내실 수 있도록 구성한 맞춤형 요약 가이드라인입니다.

---

## 🗺️ 1. Vue ➔ React 핵심 매핑 테이블

React Hooks를 완전히 새로운 개념으로 암기하려 하지 마시고, 이미 마스터하신 Vue의 핵심 기술들과 1:1로 매핑하여 연상해 보세요!

| 역할 | 🟢 Vue.js | 🔵 React.js | 핵심 차이점 및 한 줄 요약 |
| :--- | :--- | :--- | :--- |
| **상태 관리** | `ref(0)` / `reactive()` | `useState(0)` | Vue는 값이 직접 바뀌지만, React는 불변성을 지키며 반드시 `setState` 함수로만 값을 변경합니다. |
| **부수 효과** | `onMounted()`, `watch()` | `useEffect(() => {}, [])` | 외부 시스템(API 호출, DOM 조작)과 리액트 화면을 연동하는 파수꾼입니다. |
| **연산 캐싱** | `computed()` | `useMemo()` | 무거운 계산식 결과를 포스트잇에 적어 재사용하듯 캐싱합니다. |
| **함수 재활용** | (내부 자동 배칭 및 고정) | `useCallback()` | 매 렌더링마다 함수가 새로 태어나는 것을 막기 위해 함수의 메모리 주소를 고정(박제)시킵니다. |

---

## 📦 2. Hooks 핵심 직관 비유 및 정석 코드

### 1️⃣ `useState` : "금고와 보관원"
* **직관 비유**:
  * `state`는 금고 안에 들어있는 보물이고, `setState`는 금고의 보물을 안전하게 꺼내고 넣어주는 전담 **보관원**입니다.
  * 금고 문을 직접 열고 보물을 손으로 만져서 고치려 하면(`state = 10` 처럼 직접 대입) 경보기가 울립니다. 반드시 보관원(`setState`)에게 수정을 요청해야만 안전하게 보관되고 화면이 갱신됩니다.
* **코드 예시**:
  ```typescript
  const [count, setCount] = useState(0);

  // ❌ 절대 금지 (직접 대입)
  count = count + 1;

  //  올바른 정석 (보관원 호출)
  setCount(prev => prev + 1);
  ```

---

### 2️⃣ `useCallback` : "함수 박제 서랍장"
* **직관 비유**:
  * React는 화면이 다시 그려질 때마다 컴포넌트 내부의 함수들을 매번 메모리에 새로 만들어냅니다.
  * **"이 함수는 처음 만들어진 메모리 주소(정체성) 그대로 평생 재활용해!"**라고 서랍장에 단단히 못 박아 두는 도구입니다.
  * 이를 통해 자식 컴포넌트가 쓸데없이 같이 재렌더링되는 성능 낭비를 완벽히 차단합니다.
* **코드 예시**:
  ```typescript
  // 컴포넌트가 1만 번 다시 그려져도 이 함수의 메모리 주소는 단 하나로 고정됩니다.
  const handleAdd = useCallback((ticker: string) => {
    console.log("Add to Watchlist:", ticker);
  }, []); // 👈 의존성 배열이 비어있으면(마운트 시) 평생 고정
  ```

---

### 3️⃣ `useEffect` : "외부 동기화용 파수꾼"
* **직관 비유**:
  * 리액트의 통제를 벗어난 외부 영역(백엔드 API 호출, DOM 수동 조작, 타이머 등)을 감시하다가, 지정된 변수(`deps`)가 바뀔 때만 자동으로 발동하는 **감시 파수꾼**입니다.
* **정석 최적화 구조 (비동기 처리)**:
  * 이펙트 내부에서 API를 호출할 때는, 이펙트가 온전히 비동기 수명주기를 지배할 수 있도록 아래처럼 **내부 로컬 함수(IIFE 등) + 마운트 플래그**를 씌워주는 것이 React 19의 표준 정공법입니다.
  ```typescript
  useEffect(() => {
    let isMounted = true; // 1. 메모리 누수를 방지하는 안전망 설치

    async function loadData() {
      const res = await api.get("/data");
      if (isMounted) {
        setData(res.data); // 2. 마운트 상태일 때만 안전하게 상태 업데이트 (Cascading 방지)
      }
    }
    loadData();

    return () => {
      isMounted = false; // 3. 컴포넌트가 사라질 때 안전핀을 뽑아 무력화
    };
  }, [triggerKey]); // 3. 오직 triggerKey가 바뀔 때만 심플하게 자동 반응!
  ```

---

### 4️⃣ `useMemo` : "계산 결과 포스트잇"
* **직관 비유**:
  * 무거운 수학 연산이나 대량의 루프 연산을 매번 새로 계산하는 것은 비효율적입니다.
  * 계산된 결과값을 포스트잇에 적어서 모니터 옆에 붙여두고, **재료(의존성 변수)가 바뀌기 전까지는 연산을 생략하고 포스트잇 값만 계속 보여주는 캐싱 도구**입니다.
* **코드 예시**:
  ```typescript
  // 대량의 필터링 연산을 캐싱
  const filteredStocks = useMemo(() => {
    return heavyFilterLogic(stocks);
  }, [stocks]); // 👈 오직 stocks 원본이 바뀔 때만 새로 계산하고, 그 외에는 기존 결과 우려먹기!
  ```

---

## 🗂️ 3. 실무 응용 꿀팁: "동적 인라인 편집(Inline Editing) 설계"

* **직관 비유**: **"단 한 개의 레이저 포인터 기믹"**
* **상황**: 표(Table)에 100개의 번역 데이터 행이 있을 때, 특정 연필(수정) 버튼을 누른 행 하나만 입력창(`input`)으로 둔갑시키고 싶습니다.
* **❌ 초보의 실수**: 100개의 아이템마다 일일이 `isEditing` 이라는 불리언 상태를 따로 만들고 관리하려고 하여 렌더링과 코드가 꼬입니다.
* ** 정석 공식 (단일 포인터 설계)**:
  * **"지금 수정 중인 대상의 ID"**를 가리키는 단 한 개의 포인터 금고(`editingId`)와 **"수정 중인 임시 텍스트"**를 임시 보관할 단 한 개의 보관소(`editingName`)만 컴포넌트 헤더에 깔끔하게 선언합니다.
  * 렌더링을 돌릴 때 `item.id === editingId` 인지 단 한 판의 1:1 비교만 찔러서, 일치하는 녀석만 `input` 폼으로 깜짝 변신시키고 나머지는 온전한 텍스트로 보여주는 기법입니다!
* **코드 예시**:
  ```typescript
  // 1. 단 두 개의 상태 포인터만 들고 갑니다.
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState<string>("");

  return (
    <table>
      {items.map(item => (
        <tr key={item.id}>
          <td>
            {editingId === item.id ? (
              // 2. 일치하면 인라인 입력창 둔갑!
              <input
                value={editingName}
                onChange={e => setEditingName(e.target.value)}
              />
            ) : (
              // 3. 일치하지 않으면 원래 데이터 노출!
              <span>{item.name_ko}</span>
            )}
          </td>
        </tr>
      ))}
    </table>
  );
  ```

---

## 💡 헷갈릴 때 스스로 질문하는 3단계 자가진단법

1. **"화면에 보여지는 데이터인가?"** ➔ 📦 **`useState`**
2. **"API 호출이나 타이머 같은 외부 동기화 작업인가?"** ➔ 🛡️ **`useEffect`**
3. **"함수가 자식에게 내려가거나 이펙트 감시 대상인가?"** ➔ 🗄️ **`useCallback`**

---

## 파생 상태는 이펙트에서 복사하지 않기

인증 여부와 사용자명만으로 관리자 여부를 즉시 계산할 수 있다면 별도 상태로 복사하지 않습니다.

```typescript
const isAdmin = isAuthenticated && username === "admin";
```

`useEffect` 안에서 `setIsAdmin(...)`을 호출하면 원본 상태 변경, 이펙트 실행, 추가 렌더링이 연쇄적으로 발생합니다. 이펙트는 리다이렉트처럼 React 외부 시스템과 동기화하는 역할만 맡기고, 화면에서 계산 가능한 값은 렌더링 중 직접 파생합니다.

또한 `useCallback` 내부에서 참조하는 값은 의존성 배열에 포함해야 합니다.

```typescript
const fetchStatus = useCallback(async () => {
  if (!accessToken) return;
  await loadStatus();
}, [accessToken]);
```
