import fs from 'fs';
import path from 'path';
import * as cheerio from 'cheerio';

// 🌍 Languages
const TARGET_LANGS = [
  'ar','fr','de','es','it','zh','ko','pt','ru','ja',
  'nl','hi','sv','no','da','fi','th','ms','tl','id'
];

// 🌐 Your website
const BASE_URL = 'https://www.egyptphotographytours.com';

// 🆓 Free translation API
const LIBRE_API = 'https://translate.terraprint.co/translate';

// 🚫 Skip these tags
const SKIP_TAGS = `
script,
style,
link,
meta,
noscript,
svg,
code,
pre,
iframe,
img,
input,
button,
select,
textarea,
option
`;

// 📄 Get root HTML files only
const allRootHtml = fs.readdirSync('.').filter(file =>
  file.endsWith('.html') &&
  fs.statSync(file).isFile()
);

// 📌 Optional CLI usage
// node translate.js about.html contact.html
const rawArgs = process.argv.slice(2);

const filesToTranslate = rawArgs.length > 0
  ? rawArgs.filter(f => allRootHtml.includes(f))
  : allRootHtml;

// 🌐 Translate text
async function translateText(text, lang) {
  if (!text || text.trim().length < 2) return text;

  // Skip URLs/emails/numbers
  if (/^[\d\s.,%$€£¥@/:\-_=+#]+$/.test(text)) {
    return text;
  }

  try {
    const response = await fetch(LIBRE_API, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'EgyptPhotographyTours/1.0'
      },
      body: JSON.stringify({
        q: text,
        source: 'en',
        target: lang,
        format: 'text'
      })
    });

    if (!response.ok) {
      console.warn(`⚠️ API ${response.status}: ${text.substring(0, 40)}`);
      return text;
    }

    const data = await response.json();

    return data.translatedText || text;

  } catch (err) {
    console.warn(`⚠️ Translation failed: ${err.message}`);
    return text;
  }
}

// 🧠 Process HTML
async function processHtml($, lang, fileName) {

  // Only body elements
  const elements = $('body *')
    .not(SKIP_TAGS)
    .toArray();

  for (const el of elements) {

    const node = $(el);

    // Skip protected sections
    if (node.attr('data-no-translate') !== undefined) {
      continue;
    }

    // Skip complex containers
    const hasComplexChildren = node.children()
      .not('br, span, strong, em, a, i, b, small, u, sub, sup')
      .length > 0;

    if (hasComplexChildren) continue;

    const original = node.text().trim();

    if (!original) continue;

    // Skip very long text blocks
    if (original.length > 500) continue;

    const translated = await translateText(original, lang);

    if (translated !== original) {
      node.text(translated);
    }

    // Faster rate limiting
    await new Promise(r => setTimeout(r, 40));
  }

  // 🌍 HTML lang
  $('html').attr('lang', lang);

  // RTL support
  if (['ar','he','fa','ur'].includes(lang)) {
    $('html').attr('dir', 'rtl');
  } else {
    $('html').removeAttr('dir');
  }

  // 🏷️ Remove old hreflang
  $('link[rel="alternate"][hreflang]').remove();

  // 🏷️ Add hreflang tags
  ['en', ...TARGET_LANGS].forEach(l => {

    const href =
      l === 'en'
        ? `${BASE_URL}/${fileName}`
        : `${BASE_URL}/${l}/${fileName}`;

    $('head').append(`
      <link rel="alternate" hreflang="${l}" href="${href}" />
    `);
  });

  $('head').append(`
    <link rel="alternate" hreflang="x-default" href="${BASE_URL}/${fileName}" />
  `);

  // 🔗 Canonical URL
  const canonicalPath =
    lang === 'en'
      ? `${BASE_URL}/${fileName}`
      : `${BASE_URL}/${lang}/${fileName}`;

  if ($('link[rel="canonical"]').length) {
    $('link[rel="canonical"]').attr('href', canonicalPath);
  } else {
    $('head').append(`
      <link rel="canonical" href="${canonicalPath}" />
    `);
  }

  // 🌍 Meta language
  if ($('meta[name="language"]').length) {
    $('meta[name="language"]').attr('content', lang);
  }

  // 📱 Open Graph locale
  if ($('meta[property="og:locale"]').length) {

    const locale =
      lang === 'en'
        ? 'en_US'
        : `${lang}_${lang.toUpperCase()}`;

    $('meta[property="og:locale"]').attr('content', locale);
  }

  // 🌐 Language switcher active state
  $('.lang-item').removeClass('is-active');

  const targetHref =
    lang === 'en'
      ? `/${fileName}`
      : `/${lang}/${fileName}`;

  $(`.lang-item[href="${targetHref}"]`)
    .addClass('is-active');
}

// 🚀 Main
async function main() {

  if (!filesToTranslate.length) {
    console.log('ℹ️ No HTML files found.');
    return;
  }

  console.log(`📄 Files: ${filesToTranslate.join(', ')}`);

  for (const file of filesToTranslate) {

    console.log(`\n🌐 Processing ${file}`);

    const html = fs.readFileSync(file, 'utf8');

    for (const lang of TARGET_LANGS) {

      process.stdout.write(` → ${lang} `);

      try {

        const clone$ = cheerio.load(html, {
          decodeEntities: false
        });

        await processHtml(clone$, lang, file);

        // Create folder
        const outDir = path.join('.', lang);

        if (!fs.existsSync(outDir)) {
          fs.mkdirSync(outDir, { recursive: true });
        }

        // Save translated page
        fs.writeFileSync(
          path.join(outDir, file),
          clone$.html(),
          'utf8'
        );

        process.stdout.write('✅\n');

      } catch (err) {

        process.stdout.write('❌\n');
        console.error(err.message);
      }
    }
  }

  console.log('\n🎉 Translation complete.');
}

// ❌ Fatal handling
main().catch(err => {
  console.error('\n❌ Fatal Error:\n', err);
  process.exit(1);
});
