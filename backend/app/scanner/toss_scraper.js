const puppeteer = require('puppeteer');

async function scrapeRankings() {
  const browser = await puppeteer.launch({ headless: 'new' });
  const page = await browser.newPage();
  
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
    if (response.url().includes('ranking') || response.url().includes('realtime/stock')) {
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

  try {
      await page.goto('https://tossinvest.com', { waitUntil: 'networkidle2', timeout: 30000 });
      await new Promise(r => setTimeout(r, 2000));
      
      for (const tab of tabs) {
          currentTab = tab;
          try {
              await page.click(`button[value='${tab}']`);
              // Wait for API to return
              await new Promise(r => setTimeout(r, 1500));
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
