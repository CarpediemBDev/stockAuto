// 네이버 해외주식 홈의 랭킹 탭이 실제로 호출하는 공개 API를 그대로 호출한다.
// 화면 텍스트에서 대문자 덩어리를 정규식으로 긁던 이전 방식은 'S'·'P'(S&P 분해), 'ETF', 'ADR',
// 'II'(회사명 로마숫자), 'YSX'(실제 종목은 YSXT) 같은 존재하지 않는 심볼을 유니버스에 넣었다.
// 티커의 유일한 근거는 API가 돌려주는 symbolCode다.

const FRONT_API = 'https://m.stock.naver.com/front-api';
const STOCK_LIST_ENDPOINT = `${FRONT_API}/worldstock/nation/stock/list`;
const DISCUSSION_RANKING_ENDPOINT = `${FRONT_API}/discussion/ranking/list/price`;
const REALTIME_ENDPOINT = `${FRONT_API}/realTime/unified`;

const PAGE_SIZE = 50;
const REALTIME_CHUNK = 50;

// 탭 → 랭킹 정렬 코드. 네이버 홈의 각 탭이 보내는 stockPriceSortType 값과 같다.
const RANKING_TABS = [
  { key: 'NAVER_MKT_AMT', sortType: 'priceTop' }, // 거래대금
  { key: 'NAVER_VOL', sortType: 'top' },          // 거래량
  { key: 'NAVER_RISE', sortType: 'up' },          // 상승
  { key: 'NAVER_FALL', sortType: 'down' }         // 하락
];
const DISCUSSION_TAB_KEY = 'NAVER_POPULAR'; // 인기토론

const SYMBOL_PATTERN = /^[A-Z][A-Z0-9-]{0,9}$/;

const HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  Referer: 'https://m.stock.naver.com/worldstock/home'
};

function uniq(values) {
  return [...new Set(values.filter(Boolean))];
}

function chunk(values, size) {
  const out = [];
  for (let i = 0; i < values.length; i += size) {
    out.push(values.slice(i, i + size));
  }
  return out;
}

/**
 * 종류주는 네이버가 점(BRK.B), 야후·yfinance가 하이픈(BRK-B)을 쓴다.
 * 변환하지 않으면 하위 시세 조회에서 통째로 조회 실패한다.
 */
function normalizeSymbol(rawSymbol) {
  const symbol = String(rawSymbol || '').trim().toUpperCase().replace(/\./g, '-');
  return SYMBOL_PATTERN.test(symbol) ? symbol : null;
}

async function fetchJson(url, options) {
  const response = await fetch(url, { headers: HEADERS, ...options });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const payload = await response.json();
  if (payload && payload.isSuccess === false) {
    throw new Error(`API rejected: ${String(payload.message || '').slice(0, 120)}`);
  }
  return payload;
}

/** 랭킹 탭 하나를 조회해 symbolCode 목록을 돌려준다. */
async function fetchRankingSymbols(sortType) {
  const url = `${STOCK_LIST_ENDPOINT}?stockNationType=USA&stockPriceSortType=${sortType}` +
    `&page=1&pageSize=${PAGE_SIZE}`;
  const payload = await fetchJson(url);
  const stocks = (payload && payload.result && payload.result.stocks) || [];
  if (!Array.isArray(stocks) || stocks.length === 0) {
    throw new Error('empty stock list');
  }
  return uniq(stocks.map((stock) => normalizeSymbol(stock && stock.symbolCode)));
}

/**
 * 인기토론 랭킹은 심볼이 아니라 종목 식별자(WETO.O, CRCL.K, BRKb)를 준다.
 * 접미사를 잘라내 추측하지 않고 실시간 조회 API로 공식 symbolCode를 받는다.
 */
async function fetchDiscussionSymbols() {
  const url = `${DISCUSSION_RANKING_ENDPOINT}?rankingType=foreignStock&size=${PAGE_SIZE}&page=1`;
  const payload = await fetchJson(url);
  const itemCodes = (payload && payload.result && payload.result.itemCodes) || [];
  if (!Array.isArray(itemCodes) || itemCodes.length === 0) {
    throw new Error('empty discussion ranking');
  }

  const symbols = [];
  for (const part of chunk(itemCodes, REALTIME_CHUNK)) {
    try {
      const resolved = await fetchJson(REALTIME_ENDPOINT, {
        method: 'POST',
        headers: { ...HEADERS, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stockType: 'foreign',
          stockEndType: 'stock',
          codes: part,
          isNxt: false
        })
      });
      const items = (resolved && resolved.result && resolved.result.items) || {};
      for (const item of Object.values(items)) {
        const symbol = normalizeSymbol(item && item.symbolCode);
        if (symbol) symbols.push(symbol);
      }
    } catch (error) {
      console.error(`discussion symbol resolution failed for ${part.length} codes: ${error.message}`);
    }
  }
  return uniq(symbols);
}

async function scrapeNaverRankings() {
  const results = {
    NAVER_MKT_AMT: [],
    NAVER_VOL: [],
    NAVER_RISE: [],
    NAVER_FALL: [],
    NAVER_POPULAR: []
  };

  for (const tab of RANKING_TABS) {
    try {
      results[tab.key] = await fetchRankingSymbols(tab.sortType);
    } catch (error) {
      console.error(`ranking tab ${tab.key} (${tab.sortType}) failed: ${error.message}`);
    }
  }

  try {
    results[DISCUSSION_TAB_KEY] = await fetchDiscussionSymbols();
  } catch (error) {
    console.error(`discussion tab ${DISCUSSION_TAB_KEY} failed: ${error.message}`);
  }

  const total = Object.values(results).reduce((sum, list) => sum + list.length, 0);
  if (total === 0) {
    console.error('no symbols collected from any Naver tab');
  }

  console.log(JSON.stringify(results));
}

scrapeNaverRankings();
