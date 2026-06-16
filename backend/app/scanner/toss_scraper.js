const puppeteer = require('puppeteer');

function uniq(values) {
  return [...new Set(values.filter(Boolean))];
}

function normalizeTicker(rawText) {
  const lines = String(rawText || '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);

  for (const line of lines) {
    const cleaned = line.replace(/^\d+\s*/, '').trim();
    if (/^[A-Z][A-Z0-9.-]{0,9}$/.test(cleaned)) {
      return cleaned;
    }
  }
  return null;
}

async function scrapeRankings() {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  await page.setUserAgent(
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
  );
  
  // 6 tabs we want to click
  const tabs = [
      "biggest_total_amount", // 토스증권 거래대금
      "biggest_total_volume", // 토스증권 거래량
      "biggest_market_amount", // 거래대금
      "biggest_market_volume", // 거래량
      "heavy_soar", // 급상승
      "heavy_descent" // 급하락
  ];
  
  const results = {
      "TOSS_TOTAL_AMT": [],
      "TOSS_TOTAL_VOL": [],
      "TOSS_MKT_AMT": [],
      "TOSS_MKT_VOL": [],
      "TOSS_SOAR": [],
      "TOSS_DESCENT": []
  };
  
  // Mapping API request to our results structure based on current active tab
  let currentTab = "biggest_total_amount";
  const tabMapping = {
      "biggest_total_amount": "TOSS_TOTAL_AMT",
      "biggest_total_volume": "TOSS_TOTAL_VOL",
      "biggest_market_amount": "TOSS_MKT_AMT",
      "biggest_market_volume": "TOSS_MKT_VOL",
      "heavy_soar": "TOSS_SOAR",
      "heavy_descent": "TOSS_DESCENT"
  };
  
  page.on('response', async response => {
    const url = response.url();
    if (url.includes('ranking') || url.includes('realtime/stock')) {
      try {
        const json = await response.json();
        // Extract tickers from json.result or similar structure
        if (json.result && Array.isArray(json.result)) {
            const tickers = json.result.map(item => item.ticker || item.symbol || item.code).filter(Boolean);
            if (tickers.length > 0) {
                const targetKey = tabMapping[currentTab];
                // Combine and deduplicate
                results[targetKey] = [...new Set([...results[targetKey], ...tickers])];
            }
        }
      } catch (e) {}
    }
  });

  async function extractVisibleTickers() {
    return await page.evaluate(() => {
      function uniq(values) {
        return [...new Set(values.filter(Boolean))];
      }

      function normalizeTicker(rawText) {
        const lines = String(rawText || '')
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean);

        for (const line of lines) {
          const cleaned = line.replace(/^\d+\s*/, '').trim();
          if (/^[A-Z][A-Z0-9.-]{0,9}$/.test(cleaned)) {
            return cleaned;
          }
        }
        return null;
      }

      const byHref = new Map();
      for (const anchor of document.querySelectorAll('a[href*="/stocks/"][href$="/order"]')) {
        const href = anchor.href;
        if (!byHref.has(href)) {
          byHref.set(href, []);
        }
        byHref.get(href).push(anchor.innerText);
      }

      return uniq(
        [...byHref.values()]
          .map((texts) => normalizeTicker(texts.join('\n')))
          .filter(Boolean)
      );
    });
  }

  try {
      await page.goto('https://www.tossinvest.com', { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.waitForSelector('button[value], a[href*="/stocks/"][href$="/order"]', { timeout: 15000 });
      await new Promise(r => setTimeout(r, 3000));
      
      for (const tab of tabs) {
          currentTab = tab;
          try {
              const clicked = await page.evaluate((tabValue) => {
                const button = document.querySelector(`button[value="${tabValue}"]`);
                if (!button) return false;
                button.click();
                return true;
              }, tab);
              if (!clicked) {
                console.error(`Failed to find ${tab}`);
                continue;
              }
              await new Promise(r => setTimeout(r, 2000));
              const targetKey = tabMapping[currentTab];
              results[targetKey] = uniq([...results[targetKey], ...await extractVisibleTickers()]);
          } catch(e) {
              console.error(`Failed to click ${tab}`);
          }
      }
  } catch (err) {
      console.error(err);
  } finally {
      await browser.close();
  }
  
  console.log(JSON.stringify(results));
}

scrapeRankings();
