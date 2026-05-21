import fs from 'fs';
import path from 'path';
import cheerio from 'cheerio';
import fetch from 'node-fetch';

const TARGET_LANGS = ['ar','fr','de','es','it','zh','ko','pt','ru','ja','nl','hi','sv','no','da','fi','th','ms','tl','id'];
const BASE_URL = 'https://www.egyptphotographytours.com';
const LIBRE_API = 'https://libretranslate.com/translate';
const SKIP_TAGS = 'script, style, link, meta, noscript, svg, code, pre, iframe, img, input, button, select, textarea, option';

// Read ONLY root HTML files (ignores language folders)
const allRootHtml = fs.readdirSync('.').filter(f => f.endsWith('.html') && fs.statSync(f).isFile());
const rawArgs = process.argv.slice(2);
const filesToTranslate = rawArgs.length > 0 ? rawArgs.filter(f => allRootHtml.includes(f)) : allRootHtml;

async function translateText(text, lang, retries = 3) {
  if (!text || text.trim().length < 3) return text;
  if (/^[\d\s.,%$€£¥@/:\-]+$/.test(text)) return text;

  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(LIBRE_API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ q: text, source: 'en', target: lang, format: 'text' })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      return data.translatedText || text;
    } catch (err) {
      if (i === retries - 1) return text;
      await new Promise(r => setTimeout(r, 1500 * (i + 1)));
    }
  }
}

async function processHtml($, lang, fileName) {
  const elements = $(`*:not(${SKIP_TAGS})`).toArray();
  for (const el of elements) {
    const node = $(el);
    const hasComplexChildren = node.children().not('br, span, strong, em, a, i, b, small, u, sub, sup, mark').length > 0;
    if (hasComplexChildren) continue;
    const original = node.text().trim();
    if (!original) continue;
    const translated = await translateText(original, lang);
    if (translated !== original) node.html(translated.replace(/&/g, '&amp;'));
    await new Promise(r => setTimeout(r, 350));
  }

  $('html').attr('lang', lang);
  if (['ar','he','fa','ur'].includes(lang)) $('html').attr('dir', 'rtl');
  else $('html').removeAttr('dir');

  $('link[rel="alternate"][hreflang]').remove();
  ['en', ...TARGET_LANGS].forEach(l => {
    const href = l === 'en' ? `${BASE_URL}/` : `${BASE_URL}/${l}/`;
    $('head').append(`<link rel="alternate" hreflang="${l}" href="${href}" />`);
  });
  $('head').append(`<link rel="alternate" hreflang="x-default" href="${BASE_URL}/" />`);

  const canonicalPath = lang === 'en' ? `${BASE_URL}/` : `${BASE_URL}/${lang}/`;
  $('link[rel="canonical"]').attr('href', canonicalPath);

  $('meta[name="language"]').attr('content', lang);
  $('meta[property="og:locale"]').attr('content', lang === 'en' ? 'en_US' : `${lang}_${lang.toUpperCase()}`);

  $('.lang-item').removeClass('is-active');
  const targetHref = lang === 'en' ? '/' : `/${lang}/`;
  $(`.lang-item[href="${targetHref}"]`).addClass('is-active');
}

async function main() {
  if (!filesToTranslate.length) return console.log('ℹ️ No HTML files to translate.');
  for (const file of filesToTranslate) {
    const html = fs.readFileSync(file, 'utf8');
    console.log(`🌐 Processing: ${file}`);
    for (const lang of TARGET_LANGS) {
      const clone$ = cheerio.load(html, { decodeEntities: false });
      await processHtml(clone$, lang, file);
      const outDir = lang;
      if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });
      fs.writeFileSync(path.join(outDir, file), clone$.html());
      console.log(`  → ${lang} ✅`);
    }
  }
  console.log('\n🎉 Translation complete.');
}

main().catch(err => { console.error('❌', err); process.exit(1); });
