# [Implementation Plan] Phase 25: Premium UI/UX Makeover & Alert Hotfixes

This plan details the implementation of a comprehensive visual makeover and UX separation for the **OverseasScanner** technical details and **AI Sentiment analysis**, along with a hotfix for the **Telegram purchase failure notifications**.

## User Review Required

> [!IMPORTANT]
> **Smart UX Separation (Quant Score Accordion vs AI News Modal):**
> Instead of cramming both *Score Breakdown* and *AI Sentiment & Signals* into a single giant horizontal accordion row, we are separating their actions and entry points to match industry-standard trading applications (like Toss Securities):
> 
> 1. **Quant Score Breakdown (Inline Accordion):**
>    - **Action:** Clicking anywhere on the table row unfolds a beautiful, compact **Quant Score Card** inline.
>    - **Visuals:** Features the pulsing neon progress bar and a clean 2-column grid of technical factor chips (`grid-cols-2`). No longer shares space with news, making it tight, centered, and super readable.
> 
> 2. **AI News Sentiment & Signals (Premium Modal Popup):**
>    - **Action:** Clicking on the **"AI 호재 🔥" / "AI 악재 📉" / "뉴스 📰"** badges inside the ticker column opens an immersive **Holographic AI News Sentiment Modal**.
>    - **Visuals:** High-fidelity popup modal featuring:
>      - Dynamic border gradient representing the sentiment (Emerald green glow for POSITIVE, Rose red for NEGATIVE).
>      - Sleek news temperature spectrum with a pulsing white-hot LED glowing pointer (`shadow-[0_0_12px_rgba(255,255,255,0.9)] animate-pulse`).
>      - Immersive glassmorphism card for the 3-line AI summary with a stylized Quote icon and a prominent "Read Original Article ↗" action.
> 
> **Telegram Alert Hotfix:**
> Distinguish between actual **[예수금 부족] (Insufficient Cash)** and **[최소 수량 미달/단가 초과] (Minimum Lot/Price Constraint)** to prevent confusing alert messages, and apply a 1-hour `WARNING_COOLDOWN` memory cache to avoid spamming the user.

---

## Proposed Changes

### [Component 1] Frontend UI/UX Separation & Makeover

#### ⚙️ [MODIFY] [OverseasScanner.tsx](file:///d:/dev/workspace/stockAuto/frontend/components/OverseasScanner.tsx)
* **Table Badge Event Listeners:**
  - Bind a `onClick={(e) => { e.stopPropagation(); openNewsModal(item); }}` handler on the AI Sentiment/News badges so they act as a separate, highly focused entry point.
* **Inline Accordion (Quant Score Card):**
  - Adjust the accordion to span only the **Score Breakdown** module across a clean, elegant layout.
  - Implement a **2-column grid** (`grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[160px] overflow-y-auto pr-1 no-scrollbar`) for the factor checklist.
  - Apply the premium dark-mode styled cards, neon-glowing rating slider (`from-indigo-500 via-purple-500 to-pink-500`), and pulsating LED bullets.
* **AI Sentiment & Summary Modal:**
  - Create a state variable `const [selectedNewsItem, setSelectedNewsItem] = useState<ScanResult | null>(null);` to manage the modal state.
  - Render an immersive, centered modal dialog when an item is selected:
    - Backdrop blur overlay (`bg-black/60 backdrop-blur-sm`).
    - Holographic glass card with micro-shadowing (`bg-zinc-900/90 border border-zinc-800/80 shadow-[0_20px_50px_rgba(0,0,0,0.5)]`).
    - Active dynamic top-border glows and pulsing LED pointer on the temperature spectrum bar.
    - Large stylized quote styling for the AI 한글 summary, clean typography, and a prominent call-to-action button to open the original URL.

---

### [Component 2] Telegram Notification Hotfix

#### ⚙️ [MODIFY] [scheduler.py](file:///d:/dev/workspace/stockAuto/backend/app/bot/scheduler.py)
* **Distinguish Order Failures:**
  - Detect if the purchase fail is due to the stock's single share price exceeding the user's allocated slice budget (e.g., price $491 vs budget $308, resulting in quantity < 1 but with cash still remaining).
  - If budget is the issue: format message as `⚠️ [자동매수 실패 - 단가 초과 / 최소 수량 미달]` with helpful explanatory text.
  - If actual cash is the issue: format message as `⚠️ [자동매수 실패 - 예수금 부족]` only when total available account cash is genuinely insufficient.
* **Cooldown Guard:**
  - Implement a 1-hour cache guard for warnings per ticker to prevent spamming duplicate failure alerts on every scheduler loop cycle.

---

## Verification Plan

### Automated Verification
1. **Frontend Type Check:** Run `npx tsc --noEmit` and `npm run lint` inside the `frontend` folder to guarantee zero compilation and type errors.
2. **Backend Syntax Check:** Run `python -m py_compile backend/app/bot/scheduler.py` to ensure zero syntax issues.

### Manual Verification
1. Start the local server (`python run.py local`) and the development Next.js client (`npm run dev`).
2. Verify row expansion: It should *only* expand the compact Score Breakdown card inline.
3. Click the "AI 호재 🔥" badge: It should trigger the gorgeous, focused AI News Sentiment Modal. Confirm background blur, gradient borders, and responsive modal closure.
