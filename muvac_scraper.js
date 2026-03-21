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

        await page.goto('https://www.muvac.com/en/browse/vacancies?query=cello&oppSubTypes=permanent,temporary', {
            waitUntil: 'networkidle2',
            timeout: 20000
        });

        // Wait for vacancy links to appear
        await page.waitForSelector('a.btn-link[href*="/vacancy/"]', { timeout: 10000 }).catch(() => {});

        const result = await page.evaluate(() => {
            // Each vacancy card is a <li> or block containing an <a> with btn-link class
            const links = Array.from(document.querySelectorAll('a.btn-link[href*="/vacancy/"]'));
            return links.slice(0, 15).map(link => {
                // The link itself contains the title text
                const title = link.textContent.trim();
                
                // The organization is typically in the next sibling or parent container
                const card = link.closest('li') || link.parentElement.parentElement;
                const allText = card ? card.innerText.split('\n').filter(t => t.trim().length > 0) : [];
                
                // Title is usually first line, org is second line
                let org = '';
                if (allText.length > 1) {
                    // Find the line that looks like an organization (contains parentheses for country)
                    for (let i = 1; i < allText.length; i++) {
                        if (allText[i].includes('(') && allText[i].includes(')') && !allText[i].includes('days left')) {
                            org = allText[i].trim();
                            break;
                        }
                    }
                }

                return {
                    name: title,
                    organization: org,
                    url: link.href
                };
            }).filter(i => i.name && i.name.length > 0);
        });

        console.log(JSON.stringify({ data: result }));
        await browser.close();
    } catch (error) {
        console.log(JSON.stringify({ data: [], error: error.toString() }));
        process.exit(0);
    }
})();
