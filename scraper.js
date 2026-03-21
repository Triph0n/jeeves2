const puppeteer = require('puppeteer');
const fs = require('fs');

async function scrape() {
    console.log('Spouštím prohlížeč...');
    const browser = await puppeteer.launch({ headless: 'new' });
    const page = await browser.newPage();
    const results = { muvac: [], musikzeitung: [] };

    try {
        // --- 1. MUVAC ---
        console.log('Načítám Muvac...');
        await page.goto('https://www.muvac.com/en/browse/vacancies?query=cello&oppSubTypes=permanent,temporary', { waitUntil: 'networkidle2' });
        
        // Čekáme na vyrenderování seznamu
        await page.waitForSelector('li[data-test-id^="vacancy-"]', { timeout: 10000 }).catch(() => console.log('Timeout Muvac'));

        results.muvac = await page.evaluate(() => {
            const items = Array.from(document.querySelectorAll('li[data-test-id^="vacancy-"]'));
            return items.slice(0, 5).map(item => {
                const titleEl = item.querySelector('h3, .title, [data-test-id="vacancy-title"]');
                const orgEl = item.querySelector('.institution, [data-test-id="vacancy-institution"]');
                const linkEl = item.querySelector('a');
                
                // Muvac has very deep nested structure, let's try broader text extraction if specific fails
                let title = titleEl ? titleEl.innerText : '';
                let org = orgEl ? orgEl.innerText : '';
                if(!title) {
                     const texts = item.innerText.split('\n').filter(t => t.trim().length > 0);
                     title = texts[0] || 'Neznámá pozice';
                     org = texts[1] || '';
                }

                return {
                    title: title.trim(),
                    organization: org.trim(),
                    url: linkEl ? linkEl.href : ''
                };
            }).filter(i => i.title);
        });
        console.log(`Muvac nalezeno: ${results.muvac.length}`);

        // --- 2. MUSIKZEITUNG ---
        console.log('Načítám Musikzeitung...');
        await page.goto('https://www.musikzeitung.ch/stellen/?_sf_s=cello', { waitUntil: 'networkidle2' });
        
        await page.waitForSelector('.elementor-post', { timeout: 10000 }).catch(() => console.log('Timeout Musikzeitung'));

        results.musikzeitung = await page.evaluate(() => {
            const items = Array.from(document.querySelectorAll('.elementor-post'));
            return items.slice(0, 5).map(item => {
                const titleEl = item.querySelector('.elementor-post__title');
                const linkEl = item.querySelector('a');
                const excerptEl = item.querySelector('.elementor-post__excerpt p');
                return {
                    title: titleEl ? titleEl.innerText.trim() : 'Neznámá pozice',
                    organization: excerptEl ? excerptEl.innerText.trim() : '',
                    url: linkEl ? linkEl.href : ''
                };
            }).filter(i => i.title);
        });
        console.log(`Musikzeitung nalezeno: ${results.musikzeitung.length}`);

    } catch (e) {
        console.error('Chyba scraperu:', e);
    } finally {
        await browser.close();
        fs.writeFileSync('scraper_results.json', JSON.stringify(results, null, 2));
        console.log('Hotovo, uloženo do scraper_results.json');
    }
}

scrape();
