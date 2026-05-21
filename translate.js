import fs from 'fs';
import path from 'path';
import cheerio from 'cheerio';
import fetch from 'node-fetch';

// ⚙️ CONFIGURATION - 👇 REPLACE BASE_URL WITH YOUR ACTUAL URL
const TARGET_LANGS = ['ar','fr','de','es','it','zh','ko','pt','ru','ja','nl','hi','sv','no','da','fi','th','ms','tl','id'];
const BASE_URL = 'https://www.egyptphotographytours.com'; // 👈 REPLACE: GitHub Pages or custom domain
const LIBRE_API = 'https://translate.terraprint.co/translate'; // Free public mirror (no API key)
const SKIP_TAGS = 'script, style, link, meta, noscript, svg, code, pre, iframe, img, input, button, select, textarea, option, a[href]';

// Read ONLY root-level .html files (ignores folders like ar/, fr/, css/, etc.)
const allRootHtml = fs.readdirSync('.').filter(f => 
  f.endsWith('.html') && fs.statSync(f).isFile()
);

// Accept specific files from CLI: node translate.js about.html contact.html
const rawArgs = process.argv.slice(2);
const filesToTranslate = rawArgs.length > 0
  ? rawArgs.filter(f => allRootHtml.includes(f))
  : allRootHtml;

async function translateText(text, lang) {
  if (!text || text.trim().length < 3) return text;
  // Skip numbers, URLs, emails, pure symbols
  if (/^[\d\s.,%$€£¥@/:\-]+$/.test(text)) return text;

  try {
    const response = await fetch(LIBRE_API, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'EgyptPhotographyTours-CI/1.0'
      },
      body: JSON.stringify({
        q: text,
        source: 'en',
        target: lang,
        format: 'text'
      })
    });

    if (!response.ok) {
      console.warn(`⚠️ HTTP ${response.status} for "${text.substring(0, 30)}..."`);
      return text;
    }

    const data = await response.json();
    return data.translatedText || text;
  } catch (error) {
    console.warn(`⚠️ Translation failed: "${text.substring(0, 30)}..." - ${error.message}`);
    return text; // Graceful fallback to original text
  }
}

async function processHtml($, lang, fileName) {
  // 1. Translate visible text only (skip code/SEO tags)
  const elements = $(`*:not(${SKIP_TAGS})`).toArray();
  
  for (const el of elements) {
    const node = $(el);
    
    // Skip if element has complex child structure (we translate direct text only)
    const hasComplexChildren = node.children()
      .not('br, span, strong, em, a, i, b, small, u, sub, sup, mark')
      .length > 0;
    if (hasComplexChildren) continue;
    
    const original = node.text().trim();
    if (!original) continue;
    
    const translated = await translateText(original, lang);
    if (translated !== original) {
      node.html(translated.replace(/&/g, '&amp;'));
    }
    
    // Rate limit delay (respect free tier)
    await new Promise(r => setTimeout(r, 350));
  }

  // 2. Update SEO & structural tags automatically
  $('html').attr('lang', lang);
  if (['ar','he','fa','ur'].includes(lang)) {
    $('html').attr('dir', 'rtl');
  } else {
    $('html').removeAttr('dir');
  }

  // Regenerate hreflang tags
  $('link[rel="alternate"][hreflang]').remove();
  ['en', ...TARGET_LANGS].forEach(l => {
    const href = l === 'en' ? `${BASE_URL}/` : `${BASE_URL}/${l}/`;
    $('head').append(`<link rel="alternate" hreflang="${l}" href="${href}" />`);
  });
  $('head').append(`<link rel="alternate" hreflang="x-default" href="${BASE_URL}/" />`);

  // Update canonical URL
  const canonicalPath = lang === 'en' ? `${BASE_URL}/` : `${BASE_URL}/${lang}/`;
  $('link[rel="canonical"]').attr('href', canonicalPath);

  // Update meta language & Open Graph locale
  $('meta[name="language"]').attr('content', lang);
  $('meta[property="og:locale"]').attr('content', 
    lang === 'en' ? 'en_US' : `${lang}_${lang.toUpperCase()}`
  );

  // Update language switcher active state
  $('.lang-item').removeClass('is-active');
  const targetHref = lang === 'en' ? '/' : `/${lang}/`;
  $(`.lang-item[href="${targetHref}"]`).addClass('is-active');
}

async function main() {
  if (!filesToTranslate.length) {
    console.log('ℹ️ No HTML files to translate.');
    return;
  }
  
  console.log(`📄 Processing: ${filesToTranslate.join(', ')}`);
  
  for (const file of filesToTranslate) {
    const html = fs.readFileSync(file, 'utf8');
    console.log(`\n🌐 Translating: ${file}`);
    
    for (const lang of TARGET_LANGS) {
      process.stdout.write(`  → ${lang} `);
      
      // Fresh Cheerio instance per language
      const clone$ = cheerio.load(html, { decodeEntities: false });
      await processHtml(clone$, lang, file);
      
      // Create language folder if needed
      const outDir = lang;
      if (!fs.existsSync(outDir)) {
        fs.mkdirSync(outDir, { recursive: true });
      }
      
      // Write translated file
      fs.writeFileSync(path.join(outDir, file), clone$.html());
      process.stdout.write('✅\n');
    }
  }
  
  console.log('\n🎉 Translation complete. Push to deploy.');
}

main().catch(err => { 
  console.error('❌ Fatal error:', err); 
  process.exit(1); 
});
