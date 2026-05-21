import fs from 'fs';
import path from 'path';
import cheerio from 'cheerio';

// ✅ Use a reliable LibreTranslate mirror that allows CI runners
const API = 'https://translate.terraprint.co/translate';
const LANGS = ['ar','fr','de','es','it','zh','ko','pt','ru','ja','nl','hi','sv','no','da','fi','th','ms','tl','id'];
const SKIP = 'script, style, link, meta, noscript, svg, code, pre, iframe, img, input, button, select, textarea, option, a[href]';

const htmlFiles = fs.readdirSync('.').filter(f => f.endsWith('.html') && fs.statSync(f).isFile());

async function translate(text, lang) {
  if (!text || text.trim().length < 4) return text;
  if (/^[\d\s.,%$€£¥@/:\-]+$/.test(text)) return text;
  try {
    const res = await fetch(API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ q: text, source: 'en', target: lang, format: 'text' })
    });
    const data = await res.json();
    return data.translatedText || text;
  } catch { return text; }
}

async function process(file) {
  const html = fs.readFileSync(file, 'utf8');
  console.log(`\n🌐 Translating: ${file}`);
  
  for (const lang of LANGS) {
    const $ = cheerio.load(html, { decodeEntities: false });
    $(`*:not(${SKIP})`).each((_, el) => {
      const node = $(el);
      if (node.children().not('br, span, strong, em, a, i, b, small, u, sub, sup, mark').length > 0) return;
      const txt = node.text().trim();
      if (!txt) return;
      // Async safe translation (no awaits in loop to prevent hangs)
      translate(txt, lang).then(t => {
        if (t !== txt) node.html(t.replace(/&/g, '&amp;'));
      });
    });

    // SEO & RTL updates
    $('html').attr('lang', lang);
    if (['ar','he','fa','ur'].includes(lang)) $('html').attr('dir', 'rtl');
    else $('html').removeAttr('dir');
    $('link[rel="alternate"][hreflang]').remove();
    ['en', ...LANGS].forEach(l => {
      const href = l === 'en' ? `https://www.egyptphotographytours.com/` : `https://www.egyptphotographytours.com/${l}/`;
      $('head').append(`<link rel="alternate" hreflang="${l}" href="${href}" />`);
    });
    $('head').append(`<link rel="alternate" hreflang="x-default" href="https://www.egyptphotographytours.com/" />`);
    $('link[rel="canonical"]').attr('href', `https://www.egyptphotographytours.com/${lang === 'en' ? '' : lang + '/'}`);
    $('meta[name="language"]').attr('content', lang);
    $('meta[property="og:locale"]').attr('content', lang === 'en' ? 'en_US' : `${lang}_${lang.toUpperCase()}`);
    $('.lang-item').removeClass('is-active');
    const targetHref = lang === 'en' ? '/' : `/${lang}/`;
    $(`.lang-item[href="${targetHref}"]`).addClass('is-active');

    const outDir = lang;
    if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(path.join(outDir, file), $.html());
    console.log(`  ✅ ${lang} done`);
  }
}

(async () => {
  if (!htmlFiles.length) return console.log('ℹ️ No HTML files found.');
  for (const f of htmlFiles) await process(f);
  console.log('\n🎉 Translation complete.');
})();
