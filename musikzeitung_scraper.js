const puppeteer = require('puppeteer-core');
const fs = require('fs');

(async () => {
    let executablePath = '';
    const paths = [
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
        'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'
    ];
    for (const p of paths) {
        if (fs.existsSync(p)) {
            executablePath = p;
            break;
        }
    }

    if (!executablePath) {
        console.log(JSON.stringify({ data: [], error: 'No browser found' }));
        process.exit(0);
    }

    try {
        const browser = await puppeteer.launch({
            executablePath,
            headless: 'new',
            args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
        });
        const page = await browser.newPage();
        await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');

        // Navigate to "Stellen" page filtered for cello
        await page.goto('https://www.musikzeitung.ch/stellen/?_sf_s=cello', {
            waitUntil: 'networkidle2',
            timeout: 20000
        });

        // Wait for articles to appear
        await page.waitForSelector('article.Teaser__article', { timeout: 10000 }).catch(() => {});

        const result = await page.evaluate(() => {
            const articles = document.querySelectorAll('article.Teaser__article');
            const items = [];

            articles.forEach(article => {
                // Category is in span.post-category > a
                const catEl = article.querySelector('.Teaser__category .post-category a');
                const category = catEl ? catEl.textContent.trim() : '';

                // Title and link: <a> wraps <div.Teaser__header> <h3.entry-title>
                const titleEl = article.querySelector('h3.entry-title');
                const title = titleEl ? titleEl.textContent.trim() : '';

                // The <a> tag is a parent of the h3
                const linkEl = titleEl ? titleEl.closest('a') : null;
                const url = linkEl ? linkEl.href : '';

                // Organization in span.Teaser__author > p.entry-title (format: "Org Name | Date")
                const authorEl = article.querySelector('.Teaser__author p');
                let org = '';
                if (authorEl) {
                    const fullText = authorEl.textContent.trim();
                    const parts = fullText.split('|');
                    org = parts[0] ? parts[0].trim() : '';
                }

                if (title && url) {
                    items.push({
                        title: title,
                        organization: org,
                        category: category,
                        url: url
                    });
                }
            });

            return items;
        });

        console.log(JSON.stringify({ data: result }));
        await browser.close();
    } catch (error) {
        console.log(JSON.stringify({ data: [], error: error.toString() }));
        process.exit(0);
    }
})();
