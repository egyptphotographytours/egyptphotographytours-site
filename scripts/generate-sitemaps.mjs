// ============================================================
// STATIC SITE SITEMAP GENERATOR (NO CRAWLING)
// Scans the repository for .html files and builds sitemaps.
// Zero dependencies · Node >= 18
// ============================================================
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

/* ---------------------------- config ---------------------------- */
const SITE = (process.env.SITE_URL || 'https://www.egyptphotographytours.com').replace(/\/+$/, '');
const HOST = new URL(SITE).host;
const OUT_DIR = process.env.OUT_DIR || 'dist-sitemaps';
const LASTMOD = new Date().toISOString().slice(0, 10); // today

// Language folders exactly as they appear in the repo (case matters: zh-CN)
const LANG_FOLDERS = (process.env.LANGUAGES ||
  'en,ar,es,fr,de,it,pt,ru,ja,zh-CN,ko,hi,nl,sv,pl,tr,vi,th,id,cs,ro,tl,no,da,fi')
  .split(',').map(s => s.trim()).filter(Boolean);
const FOLDER_LOWER = new Map();
for (const f of LANG_FOLDERS) if (f.toLowerCase() !== 'en') FOLDER_LOWER.set(f.toLowerCase(), f);

const CHUNK = 45000;
const HTACCESS_MAX_RULES = 3000;

const TYPE_META = {
  home:     { priority: '1.0', changefreq: 'daily'   },
  category: { priority: '0.8', changefreq: 'weekly'  },
  tour:     { priority: '0.7', changefreq: 'weekly'  },
  blog:     { priority: '0.5', changefreq: 'monthly' },
  static:   { priority: '0.6', changefreq: 'yearly'  },
  page:     { priority: '0.6', changefreq: 'monthly' },
  legal:    { priority: '0.1', changefreq: 'never'   },
};

/* ---------------------------- helpers ---------------------------- */
const escXml = s => String(s).replace(/[<>&'"]/g, c => ({ '<':'&lt;','>':'&gt;','&':'&amp;',"'":'&apos;','"':'&quot;' }[c]));
const escRe  = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const chunks = (arr, n) => { const r = []; for (let i = 0; i < arr.length; i += n) r.push(arr.slice(i, i + n)); return r; };

function langOf(relPath) {
  const seg = relPath.split(path.sep)[0]?.toLowerCase();
  if (seg === 'en' || FOLDER_LOWER.has(seg)) return FOLDER_LOWER.get(seg) || 'en';
  return 'en';
}

function altKey(relPath, lang) {
  // Remove language folder prefix (if any) and .html extension
  let p = relPath;
  if (lang !== 'en' && p.startsWith(lang + path.sep)) {
    p = p.slice(lang.length + 1);
  } else if (lang === 'en' && p.startsWith('en' + path.sep)) {
    p = p.slice(3);
  }
  // Remove .html
  if (p.endsWith('.html')) p = p.slice(0, -5);
  // Convert to URL path (no trailing slash, root = '/')
  p = p.replace(/\\/g, '/');
  if (p === 'index') return '/';
  if (p.startsWith('/')) p = p.slice(1);
  return p || '/';
}

function classify(pn) {
  if (pn === '/') return 'home';
  if (/(privacy|terms|legal|cookie|refund|disclosure|gdpr)/i.test(pn)) return 'legal';
  if (/(about|contact|faq|team|careers|press|affiliate|payment|how-it-works)/i.test(pn)) return 'static';
  if (/\/(blog|articles?|news|tips|guides?)\/[^/]+\/?$/i.test(pn)) return 'blog';
  if (/\/(tours?|packages?|trips?|excursions?|day-tours?|photography-tours?|destinations?|places)\/[^/]+\/?$/i.test(pn)) return 'tour';
  if (/\/(tours?|packages?|destinations?|excursions?|gallery|blog|news|guides?|tips)\/?$/i.test(pn)) return 'category';
  return 'page';
}

/* ---------------------------- scan repository ---------------------------- */
function walkDir(dir, base = '') {
  const results = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    const rel = path.join(base, entry.name);
    if (entry.isDirectory()) {
      // Skip hidden folders and common non‑page folders
      if (entry.name.startsWith('.') || entry.name === 'node_modules' || entry.name === '.git') continue;
      results.push(...walkDir(full, rel));
    } else if (entry.isFile() && entry.name.endsWith('.html')) {
      results.push(rel);
    }
  }
  return results;
}

const repoRoot = process.cwd(); // Should be the repository root when run in workflow
const htmlFiles = walkDir(repoRoot);

// Build page objects
const pages = [];
for (const rel of htmlFiles) {
  const lang = langOf(rel);
  const key = altKey(rel, lang);
  const urlPath = key === '/' ? '/' : '/' + key;
  const url = SITE + urlPath;
  // Page title: use file name (without extension) for display
  const title = path.basename(rel, '.html');
  pages.push({
    rel,
    lang,
    key,
    url,
    path: urlPath,
    title,
    type: classify(urlPath),
    status: 200,
    noindex: false,
    soft404: false,
    canonical: url,
  });
}

if (!pages.length) {
  console.error('❌ No HTML files found in the repository. Exiting.');
  process.exit(1);
}

/* ---------------------------- build hreflang groups ---------------------------- */
const altMap = new Map();
for (const p of pages) {
  if (!altMap.has(p.key)) altMap.set(p.key, new Map());
  altMap.get(p.key).set(p.lang, p.url);
}

/* ---------------------------- write sitemaps ---------------------------- */
fs.rmSync(OUT_DIR, { recursive: true, force: true });
fs.mkdirSync(OUT_DIR, { recursive: true });

const byLang = new Map();
for (const p of pages) {
  if (!byLang.has(p.lang)) byLang.set(p.lang, []);
  byLang.get(p.lang).push(p);
}
const indexEntries = [];

function urlEntry(p) {
  const meta = TYPE_META[p.type] || TYPE_META.page;
  let x = `  <url>\n    <loc>${escXml(p.url)}</loc>\n    <lastmod>${LASTMOD}</lastmod>\n    <changefreq>${meta.changefreq}</changefreq>\n    <priority>${meta.priority}</priority>\n`;
  const alts = altMap.get(p.key);
  if (alts && alts.size > 1) {
    for (const [l, u] of [...alts.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
      x += `    <xhtml:link rel="alternate" hreflang="${l}" href="${escXml(u)}"/>\n`;
    }
    const xdef = alts.get('en') || [...alts.values()][0];
    x += `    <xhtml:link rel="alternate" hreflang="x-default" href="${escXml(xdef)}"/>\n`;
  }
  return x + '  </url>\n';
}

const langsPresent = LANG_FOLDERS.filter(f => byLang.has(f));
for (const lang of langsPresent) {
  const list = byLang.get(lang);
  const dir = lang === 'en' ? OUT_DIR : path.join(OUT_DIR, lang);
  fs.mkdirSync(dir, { recursive: true });
  const parts = chunks(list, CHUNK);
  parts.forEach((part, i) => {
    const fname = lang === 'en' ? (i ? `sitemap-en-${i + 1}.xml` : 'sitemap-en.xml')
                                : (i ? `sitemap-${i + 1}.xml` : 'sitemap.xml');
    const rel = lang === 'en' ? fname : `${lang}/${fname}`;
    let xml = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n`;
    for (const p of part) xml += urlEntry(p);
    xml += `</urlset>\n`;
    fs.writeFileSync(path.join(dir, fname), xml);
    indexEntries.push({ loc: `${SITE}/${rel}`, count: part.length });
  });
}

const indexXml = `<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
  indexEntries.map(e => `  <sitemap>\n    <loc>${escXml(e.loc)}</loc>\n    <lastmod>${LASTMOD}</lastmod>\n  </sitemap>`).join('\n') +
  `\n</sitemapindex>\n`;
fs.writeFileSync(path.join(OUT_DIR, 'sitemap.xml'), indexXml);

/* ---------------------------- robots.txt ---------------------------- */
fs.writeFileSync(path.join(OUT_DIR, 'robots.txt'), `# robots.txt — auto-generated ${LASTMOD}
User-agent: *
Allow: /
Disallow: /search
Disallow: /*?s=
Disallow: /cart
Disallow: /checkout
Disallow: /my-account/
Disallow: /login
Disallow: /wp-admin/
Disallow: /wp-login.php
Disallow: /xmlrpc.php
Disallow: /?utm_
Disallow: /?gclid=
Disallow: /?fbclid=

Sitemap: ${SITE}/sitemap.xml
`);

/* ---------------------------- .htaccess (basic security/cache) ---------------------------- */
{
  const htaccess = `# ============================================================
# AUTO-GENERATED by SEO Sitemap Factory — ${LASTMOD}
# Static site .htaccess (no redirects detected)
# ============================================================

# Force HTTPS + www
RewriteEngine On
RewriteCond %{HTTPS} off [OR]
RewriteCond %{HTTP_HOST} !^www\\.${HOST.replace(/\./g, '\\.')}$ [NC]
RewriteRule ^ https://www.${HOST}/%{REQUEST_URI} [R=301,L]

# Security headers
<IfModule mod_headers.c>
  Header always set X-Content-Type-Options "nosniff"
  Header always set X-Frame-Options "SAMEORIGIN"
  Header always set Referrer-Policy "strict-origin-when-cross-origin"
</IfModule>

# Cache
<IfModule mod_expires.c>
  ExpiresActive On
  ExpiresByType image/jpeg "access plus 1 year"
  ExpiresByType image/png "access plus 1 year"
  ExpiresByType image/webp "access plus 1 year"
  ExpiresByType image/svg+xml "access plus 1 year"
  ExpiresByType text/css "access plus 1 month"
  ExpiresByType application/javascript "access plus 1 month"
  ExpiresByType text/html "access plus 1 hour"
</IfModule>
`;
  fs.writeFileSync(path.join(OUT_DIR, '.htaccess'), htaccess);
}

/* ---------------------------- redirect rule files (empty) ---------------------------- */
fs.writeFileSync(path.join(OUT_DIR, 'redirects-apache.conf'), `# No redirects generated (static repo mode)\n`);
fs.writeFileSync(path.join(OUT_DIR, 'redirects-nginx.conf'), `# No redirects generated (static repo mode)\n`);

/* ---------------------------- HTML sitemap ---------------------------- */
{
  const LANG_NAMES = {
    en:'English', ar:'العربية', es:'Español', fr:'Français', de:'Deutsch', it:'Italiano',
    pt:'Português', ru:'Русский', ja:'日本語', 'zh-CN':'中文（简体）', ko:'한국어', hi:'हिन्दी',
    nl:'Nederlands', sv:'Svenska', pl:'Polski', tr:'Türkçe', vi:'Tiếng Việt', th:'ไทย',
    id:'Bahasa Indonesia', cs:'Čeština', ro:'Română', tl:'Filipino', no:'Norsk', da:'Dansk', fi:'Suomi',
  };
  let h = `<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>Sitemap — ${escXml(HOST)}</title>\n<style>` +
    `body{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;line-height:1.6}` +
    `h1{border-bottom:3px solid #c9a227;padding-bottom:.5rem}h2{margin-top:2rem;color:#1a3c5e}ul{columns:2;column-gap:2rem}li{margin:.25rem 0}a{color:#1a6fb5;text-decoration:none}a:hover{text-decoration:underline}@media(max-width:700px){ul{columns:1}}` +
    `</style>\n</head>\n<body>\n<h1>Sitemap</h1><p>Every page on this website, grouped by language. Updated ${LASTMOD}.</p>\n`;
  for (const lang of langsPresent) {
    const list = byLang.get(lang);
    h += `<h2>${escXml(LANG_NAMES[lang] || lang)} (${list.length})</h2>\n<ul>\n`;
    for (const p of list) {
      h += `<li><a href="${escXml(p.url)}">${escXml(p.title)}</a></li>\n`;
    }
    h += `</ul>\n`;
  }
  h += `</body>\n</html>\n`;
  fs.writeFileSync(path.join(OUT_DIR, 'sitemap.html'), h);
}

/* ---------------------------- canonicals.csv ---------------------------- */
{
  const rows = [['url', 'currentcanonical', 'suggestedcanonical', 'issue']];
  for (const p of pages) {
    rows.push([p.url, p.url, p.url, 'ok']);
  }
  const csv = rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
  fs.writeFileSync(path.join(OUT_DIR, 'canonicals.csv'), csv);
}

/* ---------------------------- SEO FIX REPORT ---------------------------- */
{
  const stats = {
    totalPages: pages.length,
    languages: langsPresent.length,
    sitemapFiles: indexEntries.length,
  };
  const md = `# 🩺 SEO Report (Static Repo Mode) — ${HOST}\n\n` +
    `Generated: ${LASTMOD}\n\n` +
    `## Summary\n` +
    `- **Total pages found:** ${pages.length}\n` +
    `- **Languages:** ${langsPresent.join(', ')}\n` +
    `- **Child sitemaps generated:** ${indexEntries.length}\n\n` +
    `All URLs are based on the \`.html\` files in the repository.\n` +
    `No crawling was performed, so no 404s or redirect chains were detected.\n` +
    `The sitemaps are ready to be submitted to Google Search Console.\n`;
  fs.writeFileSync(path.join(OUT_DIR, 'SEO-FIX-REPORT.md'), md);
}

/* ---------------------------- summary ---------------------------- */
console.log('\n========== RESULT ==========');
console.log(`Total pages      : ${pages.length}`);
console.log(`Languages        : ${langsPresent.join(', ')}`);
console.log(`Child sitemaps   : ${indexEntries.length} → index: ${SITE}/sitemap.xml`);
console.log(`lastmod (all)    : ${LASTMOD}`);
console.log(`Output dir       : ${OUT_DIR}/`);
console.log('============================\n');
