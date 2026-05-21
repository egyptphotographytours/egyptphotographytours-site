import fs from 'fs';
import path from 'path';
import cheerio from 'cheerio';
import deepl from 'deepl-node';

// ⚙️ CONFIG
const TARGET_LANGS = ['ar','fr','de','es','it','zh','ko','pt','ru','ja','nl','hi','sv','no','da','fi','th','ms','tl','id'];
const BASE_URL = 'https://www.egyptphotographytours.com'; // 👈 REPLACE with your actual domain or GitHub Pages URL
const DEEPL_KEY = process.env.DEEPL_AUTH_KEY;
if (!DEEPL_KEY) throw new Error('Missing DEEPL_AUTH_KEY');

const translator = new deepl.Translator(DEEPL_KEY);
const SKIP_TAGS = 'script, style, link, meta, noscript, svg, code, pre, iframe, img, input, button, select, textarea, option';

// Only root-level .html files (ignores ar/, fr/, css/, etc.)
const allRootHtml = fs.readdirSync('.').filter(f => f.endsWith('.html') && fs.statSync(f).isFile());

// Accept specific files from CLI: node translate.js about.html contact.html
const rawArgs = process.argv.slice(2);
const filesToTranslate = rawArgs.length > 0
  ? rawArgs.filter(f => allRootHtml.includes(f))
  : allRootHtml;

async function translateText(text, lang) {
  if (!text || text.trim().length < 3) return text;
  if (/^[\d\s.,%$€£¥@/:\-]+$/.test(text)) return text; // Skip numbers/URLs
  try {
    const res = await translator.translateText(text, null, lang.toUpperCase());
    await new Promise(r => setTimeout(r, 250)); // Respect DeepL free tier
    return res.text;
  } catch { return text; }
}

async function processHtml($, lang, fileName) {
  // 1. Translate visible text only
  const elements = $(`*:not(${SKIP_TAGS})`).toArray();
  for (const el of elements) {
    const node = $(el);
    const hasComplexChildren = node.children().not('br, span, strong, em, a, i, b, small, u, sub, sup, mark').length > 0;
    if (hasComplexChildren) continue;
    const original = node.text().trim();
    if (!original) continue;
    const translated = await translateText(original, lang);
    if (translated !== original) node.html(translated.replace(/&/g, '&amp;'));
  }

  // 2. Update SEO & structural tags
  $('html').attr('lang', lang);
  if (['ar','he','fa','ur'].includes(lang)) $('html').attr('dir', 'rtl');
  else $('html').removeAttr('dir');

  // Regenerate hreflang
  $('link[rel="alternate"][hreflang]').remove();
  ['en', ...TARGET_LANGS].forEach(l => {
    const href = l === 'en' ? `${BASE_URL}/` : `${BASE_URL}/${l}/`;
    $('head').append(`<link rel="alternate" hreflang="${l}" href="${href}" />`);
  });
  $('head').append(`<link rel="alternate" hreflang="x-default" href="${BASE_URL}/" />`);

  // Update canonical
  const canonicalPath = lang === 'en' ? `${BASE_URL}/` : `${BASE_URL}/${lang}/`;
  $('link[rel="canonical"]').attr('href', canonicalPath);

  // Update meta & OG
  $('meta[name="language"]').attr('content', lang);
  $('meta[property="og:locale"]').attr('content', lang === 'en' ? 'en_US' : `${lang}_${lang.toUpperCase()}`);

  // Update language switcher active state
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
      process.stdout.write(`  → ${lang} ✅\n`);
    }
  }
  console.log('\n🎉 Translation complete. Push to deploy.');
}

main().catch(err => { console.error('❌', err); process.exit(1); });
