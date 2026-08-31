const puppeteer = require('puppeteer');

// 토스 홈 랭킹 위젯의 탭 버튼 value → discovery 소스 태그.
const TAB_MAPPING = {
  biggest_total_amount: 'TOSS_TOTAL_AMT', // 토스증권 거래대금
  biggest_total_volume: 'TOSS_TOTAL_VOL', // 토스증권 거래량
  biggest_market_amount: 'TOSS_MKT_AMT',  // 거래대금
  biggest_market_volume: 'TOSS_MKT_VOL',  // 거래량
  heavy_soar: 'TOSS_SOAR',                // 급상승
  heavy_descent: 'TOSS_DESCENT'           // 급하락
};

// productCode를 공식 심볼로 바꾸는 토스 조회 API. 화면 텍스트를 티커로 추측하지 않기 위한 유일한 근거다.
const STOCK_INFO_ENDPOINT = 'https://wts-info-api.tossinvest.com/api/v2/stock-infos';
const STOCK_INFO_CHUNK = 100;

// 국내 시장 코드. 하위 파이프라인(yfinance)은 미국 심볼만 다루므로 여기서 걸러낸다.
const KR_MARKET_CODES = new Set(['KSQ', 'KSP', 'KNX']);
const SYMBOL_PATTERN = /^[A-Z][A-Z0-9-]{0,9}$/;

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
 * productCode 목록을 토스 조회 API로 심볼에 매핑한다.
 * 국내 종목과 심볼 형식이 깨진 항목은 여기서 탈락시킨다.
 */
async function resolveSymbols(productCodes) {
  const symbolByCode = new Map();

  for (const part of chunk(productCodes, STOCK_INFO_CHUNK)) {
    const url = `${STOCK_INFO_ENDPOINT}?codes=${encodeURIComponent(part.join(','))}`;
    try {
      const response = await fetch(url, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
            '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
          Referer: 'https://www.tossinvest.com/'
        }
      });
      if (!response.ok) {
        console.error(`stock-infos HTTP ${response.status} for ${part.length} codes`);
        continue;
      }
      const payload = await response.json();
      const rows = Array.isArray(payload && payload.result) ? payload.result : [];
      if (rows.length === 0) {
        console.error(`stock-infos returned no rows for ${part.length} codes`);
        continue;
      }
      for (const row of rows) {
        const code = row && row.code;
        // 종류주는 토스가 점(BRK.B), 야후·yfinance가 하이픈(BRK-B)을 쓴다.
        // 변환하지 않으면 하위 시세 조회에서 통째로 조회 실패한다.
        const symbol = String((row && row.symbol) || '').trim().toUpperCase().replace(/\./g, '-');
        const marketCode = (row && row.market && row.market.code) || '';
        if (!code || !symbol) continue;
        if (KR_MARKET_CODES.has(marketCode)) continue;
        if (!SYMBOL_PATTERN.test(symbol)) continue;
        symbolByCode.set(code, symbol);
      }
    } catch (error) {
      console.error(`stock-infos request failed: ${error.message || String(error)}`);
    }
  }

  return symbolByCode;
}

/**
 * 활성 탭의 랭킹 목록에서 productCode를 뽑는다.
 * 탭 버튼에서 위로 올라가며 종목 링크가 충분히 모인 최초의 조상으로 범위를 좁히기 때문에,
 * 홈 화면의 다른 섹션에 있는 종목 링크가 섞이지 않는다.
 * 반환값 null은 "탭 버튼 자체를 못 찾음"으로, 빈 배열(목록이 비어 있음)과 구분한다.
 */
function extractRankingCodesInPage(tabValue) {
  const button = document.querySelector(`button[value="${tabValue}"]`);
  if (!button) return null;

  const selector = 'a[href*="/stocks/"][href$="/order"]';
  let node = button;
  for (let depth = 0; depth < 12; depth += 1) {
    node = node.parentElement;
    if (!node) break;
    const anchors = node.querySelectorAll(selector);
    if (anchors.length >= 10) {
      const codes = Array.from(anchors, (anchor) => {
        const href = anchor.getAttribute('href') || '';
        const matched = href.match(/\/stocks\/([^/]+)\/order/);
        return matched ? matched[1] : null;
      });
      return [...new Set(codes.filter(Boolean))];
    }
  }
  return [];
}

async function scrapeRankings() {
  const results = {};
  for (const tag of Object.values(TAB_MAPPING)) {
    results[tag] = [];
  }

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  try {
    const page = await browser.newPage();
    await page.setUserAgent(
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    );

    // 랭킹 목록의 종목 로고 수백 장이 전체 시간의 3분의 2를 먹는다. 티커 추출에 쓰이지 않으므로 버린다.
    // 스타일시트는 막지 않는다 - 막으면 랭킹 위젯이 렌더되지 않아 탭 버튼조차 나오지 않는다.
    await page.setRequestInterception(true);
    page.on('request', (request) => {
      const resourceType = request.resourceType();
      if (resourceType === 'image' || resourceType === 'font' || resourceType === 'media') {
        request.abort().catch(() => {});
      } else {
        request.continue().catch(() => {});
      }
    });

    await page.goto('https://www.tossinvest.com', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForSelector('button[value], a[href*="/stocks/"][href$="/order"]', { timeout: 15000 });
    await new Promise((resolve) => setTimeout(resolve, 3000));

    // 1단계: 탭별 productCode 수집. 클릭 직후 화면을 읽으므로 응답 순서에 의존하지 않는다.
    const codesByTag = {};
    for (const [tabValue, tag] of Object.entries(TAB_MAPPING)) {
      try {
        const clicked = await page.evaluate((value) => {
          const button = document.querySelector(`button[value="${value}"]`);
          if (!button) return false;
          button.click();
          return true;
        }, tabValue);

        if (!clicked) {
          console.error(`tab button not found: ${tabValue}`);
          continue;
        }

        await new Promise((resolve) => setTimeout(resolve, 2000));
        const codes = await page.evaluate(extractRankingCodesInPage, tabValue);
        if (codes === null) {
          console.error(`tab button disappeared after click: ${tabValue}`);
          continue;
        }
        if (codes.length === 0) {
          console.error(`no ranking rows found for tab: ${tabValue}`);
          continue;
        }
        codesByTag[tag] = codes;
      } catch (error) {
        console.error(`tab ${tabValue} failed: ${error.message || String(error)}`);
      }
    }

    // 2단계: 전체 productCode를 한 번에 심볼로 해석한 뒤 탭별로 되돌려 놓는다.
    const allCodes = uniq(Object.values(codesByTag).flat());
    if (allCodes.length === 0) {
      console.error('no product codes collected from any tab');
    } else {
      const symbolByCode = await resolveSymbols(allCodes);
      if (symbolByCode.size === 0) {
        console.error(`symbol resolution produced nothing for ${allCodes.length} product codes`);
      }
      for (const [tag, codes] of Object.entries(codesByTag)) {
        results[tag] = uniq(codes.map((code) => symbolByCode.get(code)));
      }
    }
  } catch (error) {
    console.error(error.message || String(error));
  } finally {
    await browser.close();
  }

  console.log(JSON.stringify(results));
}

scrapeRankings();
