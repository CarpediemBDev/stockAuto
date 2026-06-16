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
  const tickers = new Set();
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
        for (const ticker of extractTickersFromPayload(payload)) {
          tickers.add(ticker);
        }
      } catch (error) {
        // Some intercepted responses are not JSON. They are irrelevant for ticker discovery.
      }
    });

    await page.goto('https://m.stock.naver.com/worldstock/menu/marketValue/USA', {
      waitUntil: 'domcontentloaded',
      timeout: 30000
    });
    await new Promise((resolve) => setTimeout(resolve, 3000));

    const visibleTickers = await page.evaluate(() => {
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

    for (const ticker of visibleTickers.map(normalizeTicker).filter(Boolean)) {
      tickers.add(ticker);
    }
  } catch (error) {
    console.error(error.message || String(error));
  } finally {
    await browser.close();
  }

  console.log(JSON.stringify([...tickers]));
}

scrapeNaverRankings();
