const puppeteer = require('puppeteer');

function uniq(values) {
  return [...new Set(values.filter(Boolean))];
}

function normalizeTicker(rawSymbol) {
  const symbol = String(rawSymbol || '').trim().toUpperCase();
  const normalized = symbol.split('.')[0];
  if (/^[A-Z][A-Z0-9.-]{0,9}$/.test(normalized)) {
    return normalized;
  }
  return null;
}

function extractTickersFromPayload(payload) {
  const tickers = [];

  function visit(value) {
    if (!value || typeof value !== 'object') return;

    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }

    const symbol =
      value.symbolCode ||
      value.symbol ||
      value.ticker ||
      value.stockCode ||
      value.reutersCode;
    const ticker = normalizeTicker(symbol);
    if (ticker) {
      tickers.push(ticker);
    }

    Object.values(value).forEach(visit);
  }

  visit(payload);
  return uniq(tickers);
}

async function scrapeNaverRankings() {
  const results = {
    "NAVER_MKT_AMT": [], // 거래대금
    "NAVER_VOL": [],     // 거래량
    "NAVER_RISE": [],    // 상승
    "NAVER_FALL": [],    // 하락
    "NAVER_POPULAR": []  // 인기토론
  };

  const tabs = [
    { key: "NAVER_MKT_AMT", selector: "mil.mtop" },
    { key: "NAVER_VOL", selector: "mil.top" },
    { key: "NAVER_RISE", selector: "mil.rise" },
    { key: "NAVER_FALL", selector: "mil.fall" },
    { key: "NAVER_POPULAR", selector: "mim.dsc" }
  ];

  let currentTabKey = "NAVER_MKT_AMT";

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

    page.on('response', async (response) => {
      const url = response.url();
      if (!url.includes('/api/stocks/') && !url.includes('/worldstock/api/')) {
        return;
      }

      try {
        if (response.status() !== 200) return;
        const payload = await response.json();
        const extracted = extractTickersFromPayload(payload);
        if (extracted.length > 0) {
          results[currentTabKey] = uniq([...results[currentTabKey], ...extracted]);
        }
      } catch (error) {
        // Some intercepted responses are not JSON. They are irrelevant for ticker discovery.
      }
    });

    await page.goto('https://m.stock.naver.com/worldstock/home', {
      waitUntil: 'domcontentloaded',
      timeout: 30000
    });
    
    await new Promise((resolve) => setTimeout(resolve, 3000));

    async function extractVisibleTickers() {
      const visible = await page.evaluate(() => {
        const values = [];
        const pattern = /\b[A-Z][A-Z0-9.-]{0,9}\b/g;
        for (const text of Array.from(document.querySelectorAll('a, span, strong'), (node) => node.textContent || '')) {
          const matches = text.match(pattern) || [];
          for (const match of matches) {
            values.push(match);
          }
        }
        return [...new Set(values)];
      });
      return uniq(visible.map(normalizeTicker).filter(Boolean));
    }

    for (const tab of tabs) {
      currentTabKey = tab.key;
      try {
        const clicked = await page.evaluate((sel) => {
          const input = document.querySelector(`input[data-nlog-click-area="${sel}"]`);
          if (input && input.nextElementSibling) {
            input.nextElementSibling.click();
            return true;
          }
          const elem = document.querySelector(`[data-nlog-click-area="${sel}"]`);
          if (elem) {
            elem.click();
            return true;
          }
          return false;
        }, tab.selector);

        if (!clicked) {
          // If we can't find it on home, maybe we navigate directly?
          // Fallback if click fails
          continue;
        }

        await new Promise((resolve) => setTimeout(resolve, 3000));
        
        const visibleTickers = await extractVisibleTickers();
        results[currentTabKey] = uniq([...results[currentTabKey], ...visibleTickers]);
      } catch (e) {
        // ignore individual tab error to continue others
      }
    }
  } catch (error) {
    console.error(error.message || String(error));
  } finally {
    await browser.close();
  }

  console.log(JSON.stringify(results));
}

scrapeNaverRankings();
