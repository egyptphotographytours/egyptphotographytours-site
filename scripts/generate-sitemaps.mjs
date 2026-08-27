// ==================================================================
//  OTHER FILE 1 OF 2
//  Save exactly as:  scripts/generate-sitemaps.mjs
//  (create folder "scripts" in the repo root)
// ==================================================================
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

/ ---------------------------- config ---------------------------- /
const SITE = (process.env.SITE_URL || 'https://www.egyptphotographytours.com').replace(/\/+$/, '');
const HOST = new URL(SITE).host;
const APEX = HOST.replace(/^www\./, '');
const ALLOWED_HOSTS = new Set([HOST, APEX, 'www.' + APEX]);
const MAXPAGES = Math.max(50, parseInt(process.env.MAXPAGES || '20000', 10));
const CONCURRENCY = Math.max(1, parseInt(process.env.CONCURRENCY || '8', 10));
const OUTDIR = process.env.OUTDIR || 'dist-sitemaps';
const URLSFILE = process.env.URLSFILE || 'urls.txt';
const WPMODE = (process.env.WPHTACCESS || 'yes').toLowerCase() !== 'no';
const LASTMOD = /^\d{4}-\d{2}-\d{2}$/.test(process.env.LASTMOD || '')
  ? process.env.LASTMOD
  : new Date().toISOString().slice(0, 10); // workflow run date = every lastmod

const LANG_FOLDERS = [...new Set((process.env.LANGUAGES ||
  'en,ar,es,fr,de,it,pt,ru,ja,zh-CN,ko,hi,nl,sv,pl,tr,vi,th,id,cs,ro,tl,no,da,fi')
  .split(',').map(s => s.trim()).filter(Boolean))];
const FOLDER_LOWER = new Map();
for (const f of LANGFOLDERS) if (f.toLowerCase() !== 'en') FOLDERLOWER.set(f.toLowerCase(), f);

const CHUNK = 45000;
const HTACCESSMAXRULES = 3000;
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';

const SKIP_LINK = /\.(jpe?g|png|gif|webp|svg|avif|ico|css|js|mjs|json|xml|xsl|zip|rar|gz|mp3|mp4|avi|mov|pdf|docx?|xlsx?|pptx?|woff2?|ttf|eot|csv|txt|kml|webmanifest)(\?|$)/i;
const SKIP_PATH = /(wp-admin|wp-login|wp-cron|xmlrpc|feed\/?$|trackback|replytocom|\/cart|\/checkout|\/my-account|\/login|\/register|\/search|cgi-bin|preview=true)/i;
const TRACKING = new Set(['utmsource','utmmedium','utmcampaign','utmterm','utmcontent','fbclid','gclid','yclid','msclkid','igshid','twclid','ref','mccid','mceid','ga','gl','lifat_id']);
const SOFT404_TITLE = /(404|not found|page not found|صفحة غير|غير موجود|غير موجودة|не найдена|introuvable|nicht gefunden|não encontrada|no encontrada|sayfa bulunamadı|見つかりません|未找到|페이지를 찾을 수 없습니다|ไม่พบ)/i;

const TYPE_META = {
  home:     { priority: '1.0', changefreq: 'daily'   },
  category: { priority: '0.8', changefreq: 'weekly'  },
  tour:     { priority: '0.7', changefreq: 'weekly'  },
  blog:     { priority: '0.5', changefreq: 'monthly' },
  static:   { priority: '0.6', changefreq: 'yearly'  },
  page:     { priority: '0.6', changefreq: 'monthly' },
  legal:    { priority: '0.1', changefreq: 'never'   },
};
const LANG_NAMES = {
  en:'English', ar:'العربية', es:'Español', fr:'Français', de:'Deutsch', it:'Italiano',
  pt:'Português', ru:'Русский', ja:'日本語', 'zh-CN':'中文（简体）', ko:'한국어', hi:'हिन्दी',
  nl:'Nederlands', sv:'Svenska', pl:'Polski', tr:'Türkçe', vi:'Tiếng Việt', th:'ไทย',
  id:'Bahasa Indonesia', cs:'Čeština', ro:'Română', tl:'Filipino', no:'Norsk', da:'Dansk', fi:'Suomi',
};

/ ---------------------------- helpers ---------------------------- /
const sleep = ms => new Promise(r => setTimeout(r, ms));
const escXml = s => String(s).replace(/[<>&'"]/g, c => ({ '':'&gt;','&':'&amp;',"'":'&apos;','"':'&quot;' }[c]));
const escRe  = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const decodeXml = s => s.replace(/&amp;/g,'&').replace(/&lt;/g,'').replace(/&quot;/g,'"').replace(/&apos;/g,"'").replace(/&#(\d+);/g, (_,n)=>String.fromCharCode(+n));
const attr = (tag, name) => { const m = String(tag).match(new RegExp(name + '\\s=\\s"\'["\']', 'i')); return m ? m[1].trim() : ''; };
const segsOf = p => p.split('/').filter(Boolean);

function normalize(raw) {
  let u; try { u = new URL(raw, SITE); } catch { return null; }
  if (!ALLOWED_HOSTS.has(u.host) || !/^https?:$/.test(u.protocol)) return null;
  u.protocol = 'https:'; u.host = HOST;
  u.hash = '';
  for (const k of [...u.searchParams.keys()]) if (TRACKING.has(k.toLowerCase())) u.searchParams.delete(k);
  u.search = ''; // clean-URL policy: drop ALL query strings
  let p = u.pathname.replace(/\/{2,}/g, '/');
  if (p.length > 1 && !path.extname(p) && !p.endsWith('/')) p += '/';
  if (!p) p = '/';
  u.pathname = p;
  return u.toString();
}
function langOf(pn) {
  const seg = (segsOf(pn)[0] || '').toLowerCase();
  if (seg === 'en') return 'en';
  return FOLDERLOWER.has(seg) ? FOLDERLOWER.get(seg) : 'en';
}
function altKey(pn, lang) {
  if (lang === 'en') return pn.replace(/^\/en(?=\/|$)/i, '') || '/';
  return pn.replace(new RegExp('^\\/' + escRe(lang) + '(?=\\/|$)', 'i'), '') || '/';
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
function chunks(arr, n) { const r = []; for (let i = 0; i  [i]);
  for (let j = 1; j  ctrl.abort(), ms);
  try {
    const res = await fetch(url, { signal: ctrl.signal, redirect: 'follow', headers: { 'user-agent': UA, accept } });
    if (!res.ok) return null;
    return await res.text();
  } catch { return null; }
  finally { clearTimeout(t); }
}
async function harvestSitemap(url, depth = 0) {
  if (depth > 2 || sitemapSeen.has(url)) return;
  sitemapSeen.add(url);
  const txt = await fetchText(url);
  if (!txt || !/]/i.test(txt)) return;
  const locs = [...txt.matchAll(/\s([^/gi)].map(m => decodeXml(m[1]).trim());
  if (/ ${locs.length} child sitemaps);
    for (const l of locs) {
      if (!/^https?:/i.test(l)) continue;
      try { await harvestSitemap(new URL(l, url).toString(), depth + 1); } catch {}
    }
  } else {
    let added = 0;
    for (const l of locs) {
      if (!/^https?:/i.test(l)) continue;
      let abs; try { abs = new URL(l, url).toString(); } catch { continue; }
      if (!foundLocs.has(abs)) { foundLocs.add(abs); added++; }
    }
    console.log(  - sitemap: ${url} -> ${added} new URLs);
  }
}
async function seedPhase() {
  console.log('PHASE 1 - harvesting URLs from existing sitemaps & robots.txt ...');
  const candidates = new Set([
    ${SITE}/sitemap.xml, ${SITE}/sitemap_index.xml, ${SITE}/sitemap-index.xml,
    ${SITE}/wp-sitemap.xml, ${SITE}/post-sitemap.xml, ${SITE}/page-sitemap.xml,
    ${SITE}/category-sitemap.xml, ${SITE}/product-sitemap.xml, ${SITE}/author-sitemap.xml,
    ${SITE}/sitemap-en.xml,
  ]);
  for (const f of LANG_FOLDERS) {
    if (f === 'en') continue;
    candidates.add(${SITE}/${f}/sitemap.xml);
    candidates.add(${SITE}/sitemap-${f}.xml);
    candidates.add(${SITE}/${f}/sitemap_index.xml);
  }
  const robots = await fetchText(${SITE}/robots.txt, 15000, 'text/plain,/');
  if (robots) for (const m of robots.matchAll(/^\sSitemap:\s(\S+)/gim)) {
    try { candidates.add(new URL(m[1], SITE).toString()); } catch {}
  }
  for (const c of candidates) await harvestSitemap(c, 0);
  let n = 0;
  for (const raw of foundLocs) if (enqueue(raw, true)) n++;
  console.log(  => ${n} unique URLs seeded from existing sitemaps.);

  if (fs.existsSync(URLS_FILE)) {
    const lines = fs.readFileSync(URLS_FILE, 'utf8').split(/\r?\n/).map(s => s.trim()).filter(s => s && !s.startsWith('#'));
    let addedFromFile = 0;
    for (const l of lines) {
      let abs; try { abs = new URL(l, SITE).toString(); } catch { continue; }
      if (enqueue(abs, true)) addedFromFile++;
    }
    console.log(  => ${addedFromFile} extra URLs from ${URLS_FILE}.);
  }
}

/ ---------------- PHASE 2: fetch pages + follow links ---------------- /
async function fetchChain(startUrl) {
  let cur = startUrl;
  const chain = [];
  for (let hop = 0; hop  ctrl.abort(), 25000);
    let res;
    try {
      res = await fetch(cur, {
        redirect: 'manual', signal: ctrl.signal,
        headers: { 'user-agent': UA, 'accept': 'text/html,application/xhtml+xml,/' },
      });
    } finally { clearTimeout(t); }
    if ([301, 302, 303, 307, 308].includes(res.status)) {
      const loc = res.headers.get('location');
      try { res.body?.cancel?.(); } catch {}
      if (!loc) return { finalUrl: cur, status: res.status, chain, res: null };
      const nextU = new URL(loc, cur);
      if (!ALLOWED_HOSTS.has(nextU.host)) {
        chain.push({ from: cur, status: res.status, to: nextU.toString() });
        return { finalUrl: nextU.toString(), status: res.status, chain, res: null, external: true };
      }
      const next = nextU.toString();
      chain.push({ from: cur, status: res.status, to: next });
      if (chain.length >= 7 || chain.some(h => h.from === next)) return { finalUrl: next, status: -1, chain, res: null, loop: true };
      cur = next; continue;
    }
    return { finalUrl: cur, status: res.status, chain, res };
  }
  return { finalUrl: cur, status: -1, chain, res: null, loop: true };
}
async function fetchChainSafe(url) {
  try { return await fetchChain(url); }
  catch { await sleep(800); return await fetchChain(url); }
}

function addSynthetic(url) {
  const pn = new URL(url).pathname;
  const lang = langOf(pn);
  unverified.push(url);
  pages.push({
    url, path: pn, segs: segsOf(pn), lang, key: altKey(pn, lang),
    title: '', canonical: url, noindex: false, soft404: false, words: 0,
    hash: crypto.createHash('sha1').update('unv:' + url).digest('hex'),
    type: classify(pn), status: 200, unverified: true,
  });
}

async function crawl(url) {
  await sleep(20);
  const r = await fetchChainSafe(url);
  if (r.loop) { problems.loops.push({ url, chain: r.chain }); return; }
  if (r.external) { problems.externalRedirects.push({ url, chain: r.chain }); return; }
  if (r.chain.length >= 1) problems.chains.push({ url, final: r.finalUrl, chain: r.chain });

  const finalNorm = normalize(r.finalUrl) || r.finalUrl;
  if (finalNorm !== url) {
    if (seen.has(finalNorm)) { try { r.res?.body?.cancel?.(); } catch {} return; }
    seen.add(finalNorm);
  }
  const status = r.status;
  if (status === 404 || status === 410) { problems.notFound.push({ url: finalNorm, discoveredAs: url, status }); return; }
  if (status >= 500) { problems.serverError.push({ url: finalNorm, status }); return; }
  if (status >= 400) { problems.other4xx.push({ url: finalNorm, status }); return; }
  if (status !== 200 || !r.res) { try { r.res?.body?.cancel?.(); } catch {} return; }

  const ct = r.res.headers.get('content-type') || '';
  if (!/text\/html/i.test(ct)) { try { r.res.body?.cancel?.(); } catch {} return; }
  const html = await r.res.text();

  const title = (html.match(/]>([\s\S]?)/i)?.[1] || '').replace(/\s+/g, ' ').trim();
  const canonicalTag = html.match(/]+rel=["']canonical["'][^>]*>/i)?.[0] || '';
  const canonicalRaw = attr(canonicalTag, 'href');
  const metaRobotsTag = html.match(/]+name=["']robots["'][^>]*>/i)?.[0] || '';
  const noindex = /noindex/i.test(attr(metaRobotsTag, 'content'));

  const text = html
    .replace(/]>[\s\S]?/gi, ' ')
    .replace(/]>[\s\S]?/gi, ' ')
    .replace(/]>[\s\S]?/gi, ' ')
    .replace(/]+>/g, ' ')
    .replace(/&[a-z#0-9]+;/gi, ' ')
    .replace(/\s+/g, ' ').trim();
  const words = text ? text.split(' ').length : 0;
  const hash = crypto.createHash('sha1').update(text.toLowerCase()).digest('hex');

  const pn = new URL(finalNorm).pathname;
  const soft404 = words ]+href\s=\s["'][^"']["'][^>]>/gi) || [];
  for (const tag of anchors) {
    const href = attr(tag, 'href');
    if (!href || /^(mailto:|tel:|javascript:|#|data:)/i.test(href)) continue;
    if (SKIPLINK.test(href) || SKIPPATH.test(href)) continue;
    let abs; try { abs = new URL(href, finalNorm).toString(); } catch { continue; }
    enqueue(abs, false);
  }
  if (pages.length % 500 === 0) console.log(... ${pages.length} HTML pages processed, queue ${queue.length});
}

let inflight = 0;
async function worker() {
  for (;;) {
    const url = queue.shift();
    if (!url) { if (inflight === 0) return; await sleep(100); continue; }
    if (pages.length + problems.notFound.length >= MAX_PAGES) return;
    inflight++;
    try { await crawl(url); }
    catch (e) {
      if (seeded.has(url)) addSynthetic(url);
      else problems.fetchErrors.push({ url, error: String(e?.message || e) });
    }
    inflight--;
  }
}

/ ---------------------------- run ---------------------------- /
enqueue(SITE + '/', false);
await seedPhase();
console.log(PHASE 2 - fetching ${queue.length} queued URLs with ${CONCURRENCY} workers ...);
const t0 = Date.now();
await Promise.all(Array.from({ length: CONCURRENCY }, () => worker()));
console.log(Done in ${((Date.now() - t0) / 1000).toFixed(1)}s - ${pages.length} pages processed.);

/ ---------------------------- analysis ---------------------------- /
const ok = pages
  .filter(p => p.status === 200 && !p.noindex && !p.soft404)
  .sort((a, b) => a.url.localeCompare(b.url));
const okSet = new Set(ok.map(p => p.url));

const altMap = new Map();
for (const p of ok) {
  if (!altMap.has(p.key)) altMap.set(p.key, new Map());
  altMap.get(p.key).set(p.lang, p.url);
}

const missingCanonical = ok.filter(p => !p.canonical).map(p => p.url);
const canonicalMismatch = ok.filter(p => p.canonical && p.canonical !== p.url)
  .map(p => ({ url: p.url, canonical: p.canonical, targetInSitemap: okSet.has(p.canonical) }));

const byHash = new Map();
for (const p of ok) { (byHash.get(p.hash) || byHash.set(p.hash, []).get(p.hash)).push(p); }
const dupGroups = [...byHash.values()].filter(g => g.length > 1).map(g => {
  const sorted = [...g].sort((a, b) => (a.segs.length - b.segs.length) || (a.url.length - b.url.length) || (a.lang === 'en' ? -1 : 1));
  return { canonical: sorted[0].url, alternates: sorted.slice(1).map(p => p.url) };
});
const dupMemberCanonical = new Map();
for (const g of dupGroups) for (const alt of g.alternates) dupMemberCanonical.set(alt, g.canonical);

const soft404Pages = pages.filter(p => p.status === 200 && p.soft404).map(p => ({ url: p.url, words: p.words, title: p.title.slice(0, 80) }));
const noindexPages = pages.filter(p => p.noindex).map(p => p.url);
const dirty = {
  uppercase: ok.filter(p => /[A-Z]/.test(p.path.replace(/^\/(zh-CN)(?=\/|$)/i, ''))).map(p => p.url),
  underscore: ok.filter(p => p.path.includes('_')).map(p => p.url),
};

const byFirst = new Map();
for (const p of ok) { const f = p.segs[0] || '/'; if (!byFirst.has(f)) byFirst.set(f, []); byFirst.get(f).push(p); }
function bestMatch(deadPath) {
  const dSegs = segsOf(deadPath);
  const first = dSegs[0] || '';
  let pool = byFirst.get(first) || [];
  if (!pool.length) pool = ok.slice(0, 4000);
  if (pool.length > 4000) pool = pool.slice(0, 4000);
  const deadSet = new Set(dSegs);
  const scored = [];
  for (const p of pool) {
    let inter = 0; for (const s of p.segs) if (deadSet.has(s)) inter++;
    const uni = deadSet.size + p.segs.length - inter || 1;
    scored.push({ p, j: inter / uni });
  }
  scored.sort((a, b) => b.j - a.j);
  const deadSlug = (dSegs[dSegs.length - 1] || '').slice(0, 40);
  let best = null, bestScore = -1;
  for (const { p, j } of scored.slice(0, 20)) {
    const slug = (p.segs[p.segs.length - 1] || '').slice(0, 40);
    const dist = levenshtein(deadSlug, slug);
    const score = j  0.6 + (1 - dist / Math.max(deadSlug.length, slug.length, 1))  0.4;
    if (score > bestScore) { bestScore = score; best = p; }
  }
  if (best && bestScore >= 0.35) return { to: best.url, confidence: (bestScore * 100).toFixed(0) + '%' };
  const cat = (byFirst.get(first) || []).find(p => p.path === /${first}/);
  if (cat) return { to: cat.url, confidence: 'category' };
  return { to: SITE + '/', confidence: 'homepage' };
}
const redirectSuggestions = [];
for (const d of problems.notFound) {
  let deadPath = '/'; try { deadPath = new URL(d.url).pathname; } catch {}
  const m = bestMatch(deadPath);
  redirectSuggestions.push({ from: deadPath, fromUrl: d.url, to: m.to, confidence: m.confidence });
}
for (const c of problems.chains) {
  try {
    const fromPath = new URL(c.url).pathname;
    const toNorm = normalize(c.final);
    if (toNorm && toNorm !== c.url && okSet.has(toNorm)) {
      redirectSuggestions.push({ from: fromPath, fromUrl: c.url, to: toNorm, confidence: 'chain-flatten' });
    }
  } catch {}
}
const dedupRedirects = [...new Map(redirectSuggestions.map(r => [r.from, r])).values()];
const rank = r => r.confidence === 'chain-flatten' ? 0 : /^\d+%$/.test(r.confidence) ? 1 : 2;
dedupRedirects.sort((a, b) => rank(a) - rank(b) || (parseInt(b.confidence) || 0) - (parseInt(a.confidence) || 0) || a.from.localeCompare(b.from));

/ ---------------------------- emit sitemaps ---------------------------- /
fs.rmSync(OUT_DIR, { recursive: true, force: true });
fs.mkdirSync(OUT_DIR, { recursive: true });

const byLang = new Map();
for (const p of ok) { if (!byLang.has(p.lang)) byLang.set(p.lang, []); byLang.get(p.lang).push(p); }
const indexEntries = [];

function urlEntry(p) {
  const meta = TYPEMETA[p.type] || TYPEMETA.page;
  let x =   \n    ${escXml(p.url)}\n    ${LASTMOD}\n    ${meta.changefreq}\n    ${meta.priority}\n;
  const alts = altMap.get(p.key);
  if (alts && alts.size > 1) {
    for (const [l, u] of [...alts.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
      x +=     \n;
    }
    const xdef = alts.get('en') || [...alts.values()][0];
    x +=     \n;
  }
  return x + '  \n';
}

const langsPresent = LANG_FOLDERS.filter(f => byLang.has(f));
for (const lang of langsPresent) {
  const list = byLang.get(lang);
  const dir = lang === 'en' ? OUTDIR : path.join(OUTDIR, lang);
  fs.mkdirSync(dir, { recursive: true });
  const parts = chunks(list, CHUNK);
  parts.forEach((part, i) => {
    const fname = lang === 'en' ? (i ? sitemap-en-${i + 1}.xml : 'sitemap-en.xml')
                                : (i ? sitemap-${i + 1}.xml : 'sitemap.xml');
    const rel = lang === 'en' ? fname : ${lang}/${fname};
    let xml = \n\n;
    for (const p of part) xml += urlEntry(p);
    xml += \n;
    fs.writeFileSync(path.join(dir, fname), xml);
    indexEntries.push({ loc: ${SITE}/${rel}, count: part.length });
  });
}

const indexXml = \n\n +
  indexEntries.map(e =>   \n    ${escXml(e.loc)}\n    ${LASTMOD}\n  ).join('\n') +
  \n\n;
fs.writeFileSync(path.join(OUT_DIR, 'sitemap.xml'), indexXml);

/ ---------------------------- robots.txt ---------------------------- /
fs.writeFileSync(path.join(OUT_DIR, 'robots.txt'), # robots.txt - auto-generated ${LASTMOD}
User-agent: *
Allow: /
Disallow: /search
Disallow: /?s=
Disallow: /?replytocom=
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
Allow: /wp-admin/admin-ajax.php

Sitemap index - submit THIS URL in Google Search Console
Sitemap: ${SITE}/sitemap.xml
);

/ ---------------------------- .htaccess ---------------------------- /
{
  const hostEsc = HOST.replace(/\./g, '\\.');
  const htRules = dedupRedirects.slice(0, HTACCESSMAXRULES).map(r => {
    const clean = r.from.replace(/^\/+|\/+$/g, '');
    const pat = clean ? ^${escRe(clean)}/?$ : '^$';
    return RewriteRule ${pat} ${r.to} [R=301,L];
  }).join('\n');
  const extraNote = dedupRedirects.length > HTACCESSMAXRULES
    ? # ... ${dedupRedirects.length - HTACCESSMAXRULES} more rules kept in redirects-apache.conf\n
    : '';
  const wpBlock = WP_MODE ? # BEGIN WordPress

RewriteEngine On
RewriteBase /
RewriteRule ^index\\.php$ - [L]
RewriteCond %{REQUEST_FILENAME} !-f
RewriteCond %{REQUEST_FILENAME} !-d
RewriteRule . /index.php [L]

END WordPress
 : # WordPress block disabled (workflow input wordpress=no). If this IS WordPress, switch it back to yes!;
  const htaccess = # ============================================================
AUTO-GENERATED by SEO Sitemap Factory - ${LASTMOD}
Replaces the previous .htaccess (old copy stays in git history).
============================================================

RewriteEngine On
RewriteBase /

Force HTTPS + www (one canonical host)
RewriteCond %{HTTPS} off [OR]
RewriteCond %{HTTP_HOST} !^www\\.${hostEsc}$ [NC]
RewriteRule ^ https://www.${HOST}%{REQUEST_URI} [R=301,L]

Auto-matched 301 fixes for 404s + flattened redirect chains
${htRules}
${extraNote}
Block junk bots
RewriteCond %{HTTPUSERAGENT} ^(mj12|dotbot|petalbot|mauibot|semrushbot|ahrefsbot) [NC]
RewriteRule ^ - [F,L]

  Header always set X-Content-Type-Options "nosniff"
  Header always set X-Frame-Options "SAMEORIGIN"
  Header always set Referrer-Policy "strict-origin-when-cross-origin"

  ExpiresActive On
  ExpiresByType image/jpeg "access plus 1 year"
  ExpiresByType image/png "access plus 1 year"
  ExpiresByType image/webp "access plus 1 year"
  ExpiresByType image/svg+xml "access plus 1 year"
  ExpiresByType text/css "access plus 1 month"
  ExpiresByType application/javascript "access plus 1 month"
  ExpiresByType text/html "access plus 1 hour"

${wpBlock};
  fs.writeFileSync(path.join(OUT_DIR, '.htaccess'), htaccess);
}

/ ---------------------------- redirect files ---------------------------- /
{
  let apache = # AUTO-GENERATED ${LASTMOD} - FULL list of 301 rules (${dedupRedirects.length} rules)\n# First ${HTACCESSMAXRULES} already included in .htaccess; this file is the master list.\n\nRewriteEngine On\n;
  let nginx = # AUTO-GENERATED ${LASTMOD} - include inside your server { } block (nginx)\n;
  for (const r of dedupRedirects) {
    const clean = r.from.replace(/^\/+|\/+$/g, '');
    apache += RewriteRule ^${escRe(clean)}/?$ ${r.to} [R=301,L]\n;
    nginx += location = ${r.from} { return 301 ${r.to}; }\n;
  }
  fs.writeFileSync(path.join(OUT_DIR, 'redirects-apache.conf'), apache);
  fs.writeFileSync(path.join(OUT_DIR, 'redirects-nginx.conf'), nginx);
}

/ ---------------------------- HTML sitemap ---------------------------- /
{
  let h = \n\n\n\n\nSitemap - ${escXml(HOST)}\n +
    body{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;line-height:1.6} +
    h1{border-bottom:3px solid #c9a227;padding-bottom:.5rem}h2{margin-top:2rem;color:#1a3c5e}ul{columns:2;column-gap:2rem}li{margin:.25rem 0}a{color:#1a6fb5;text-decoration:none}a:hover{text-decoration:underline}@media(max-width:700px){ul{columns:1}} +
    \n\n\nSitemapEvery page of this website, grouped by language. Updated ${LASTMOD}.\n;
  for (const lang of langsPresent) {
    h += ${escXml(LANG_NAMES[lang] || lang)} (${byLang.get(lang).length})\n\n;
    for (const p of byLang.get(lang)) h += ${escXml(p.title || p.path)}\n;
    h += \n;
  }
  h += \n\n;
  fs.writeFileSync(path.join(OUT_DIR, 'sitemap.html'), h);
}

/ ---------------------------- canonicals.csv ---------------------------- /
{
  const rows = [['url', 'currentcanonical', 'suggestedcanonical', 'issue']];
  for (const p of ok) {
    const suggested = dupMemberCanonical.get(p.url) || p.url;
    let issue = 'ok';
    if (p.unverified) issue = 'unverified-from-old-sitemap';
    else if (!p.canonical) issue = 'missing-canonical';
    else if (dupMemberCanonical.get(p.url) && p.canonical === dupMemberCanonical.get(p.url)) issue = 'duplicate-member-canonical-correct';
    else if (dupMemberCanonical.get(p.url)) issue = 'duplicate-needs-canonical';
    else if (p.canonical !== p.url) issue = 'canonical-mismatch';
    rows.push([p.url, p.canonical, suggested, issue]);
  }
  const csv = rows.map(r => r.map(v => "${String(v).replace(/"/g, '""')}").join(',')).join('\n');
  fs.writeFileSync(path.join(OUT_DIR, 'canonicals.csv'), csv);
}

/ ---------------------------- SEO FIX REPORT ---------------------------- /
{
  const cap = (arr, n = 100) => arr.length > n ? arr.slice(0, n).map(String).concat([... and ${arr.length - n} more (see audit.json / canonicals.csv)]) : arr.map(String);
  const stats = {
    crawledHtml: pages.length, indexedInSitemaps: ok.length, languages: langsPresent,
    seededFromOldSitemaps: seeded.size, unverifiedIncluded: unverified.length,
    notFound: problems.notFound.length, server5xx: problems.serverError.length,
    redirectChains: problems.chains.length, redirectLoops: problems.loops.length,
    soft404: soft404Pages.length, missingCanonical: missingCanonical.length,
    canonicalMismatch: canonicalMismatch.length, duplicateGroups: dupGroups.length,
    noindex: noindexPages.length, uppercaseUrls: dirty.uppercase.length,
    underscoreUrls: dirty.underscore.length, fetchErrors: problems.fetchErrors.length,
    redirectRules: dedupRedirects.length, lastmodAppliedToAll: LASTMOD,
  };
  fs.writeFileSync(path.join(OUT_DIR, 'audit.json'),
    JSON.stringify({ generatedAt: new Date().toISOString(), stats, problems, dupGroups, unverified: unverified.slice(0, 5000), redirectSuggestions: dedupRedirects.slice(0, 8000) }, null, 2));

  let md = # SEO FIX REPORT - ${HOST}\n\n +
    Run: ${LASTMOD} - every lastmod = ${LASTMOD} - ${indexEntries.length} child sitemaps - ${ok.length} URLs - languages: ${langsPresent.join(', ')}\n\n +
    URL discovery: ${seeded.size} URLs seeded from your old sitemaps/robots.txt - ${unverified.length} included without live re-verification - ${problems.notFound.length} dead URLs from old sitemaps converted into 301 rules.\n\n +
    ## What this run already fixed automatically\n +
    - Replaced: /sitemap.xml (index), /sitemap-en.xml, every //sitemap.xml, /robots.txt, /.htaccess, redirect files.\n +
    - Reciprocal hreflang (xhtml:link + x-default) on every URL that has translations.\n +
    - Self-canonical map -> canonicals.csv (apply via Rank Math / Yoast).\n +
    - Only final-200 URLs listed (no redirects, no 404s, no noindex, no soft-404s).\n +
    - .htaccess: HTTPS+www canonicalization, ${Math.min(dedupRedirects.length, HTACCESSMAXRULES)} smart 301 rules, cache + security headers${WP_MODE ? ', WordPress core rules preserved' : ''}.\n\n +
    ## Your GSC errors -> fix location\n +
    | GSC error | Fix delivered |\n|---|---|\n +
    | Alternate page with proper canonical tag (1,503) | Healthy - keep canonicals.csv consistent |\n +
    | Crawled - currently not indexed (465) | Thin pages removed from sitemap; HTML sitemap; enrich content |\n +
    | Not found 404 (5,033) | .htaccess + redirects-apache.conf 301 rules + excluded from sitemap |\n +
    | Duplicate without user-selected canonical (1,559) | canonicals.csv -> set suggested canonicals |\n +
    | Page with redirect (94) | Only final-200 URLs listed; chains flattened |\n +
    | Redirect error (4) | Loop list below - break the loop |\n +
    | Soft 404 (1) | List below - return real 404 or add content |\n +
    | Server error 5xx (1) | List below - fix server, then "Validate fix" |\n +
    | Duplicate, Google chose different canonical (33) | Self-canonicals + hreflang consistency |\n +
    | Discovered - currently not indexed | Clean sitemap, internal linking, resubmit index |\n\n +
    ## Next steps\n +
    1. Sync your hosting with the GitHub repo (files already pushed).\n +
    2. GSC -> Sitemaps -> remove old ones -> submit ${SITE}/sitemap.xml.\n +
    3. Link /sitemap.html in your footer.\n +
    4. After 24-72h click Validate fix on each GSC report.\n\n +
    ## Included without live re-verification (${unverified.length})\n +
    ${unverified.length ? 'These URLs were in YOUR old sitemaps but did not answer during this run. Check a sample manually.\n' + cap(unverified, 50).map(s => - ${s}).join('\n') : '- none'}\n\n +
    ## Detected issues\n +
    ### Redirect loops (${problems.loops.length})\n${problems.loops.length ? cap(problems.loops.map(l => ${l.url} -> ${l.chain.map(c => c.to).join(' -> ')}), 50).map(s => - ${s}).join('\n') : '- none'}\n\n +
    ### Redirect chains flattened (${problems.chains.length})\n${problems.chains.length ? cap(problems.chains.slice(0, 50).map(c => ${c.url} -> ${c.final}), 50).map(s => - ${s}).join('\n') : '- none'}\n\n +
    ### 404 / 410 (${problems.notFound.length})\n${problems.notFound.length ? cap(problems.notFound.map(d => d.url), 100).map(s => - ${s}).join('\n') : '- none'}\n\n +
    ### Soft 404s (${soft404Pages.length})\n${soft404Pages.length ? cap(soft404Pages.map(s => ${s.url} (about ${s.words} words, "${s.title}")), 50).map(s => - ${s}).join('\n') : '- none'}\n\n +
    ### Server errors 5xx (${problems.serverError.length})\n${problems.serverError.length ? cap(problems.serverError.map(s => s.url), 50).map(s => - ${s}).join('\n') : '- none'}\n\n +
    ### Missing canonical (${missingCanonical.length})\n${missingCanonical.length ? cap(missingCanonical, 100).map(s => - ${s}).join('\n') : '- none'}\n\n +
    ### Canonical mismatch (${canonicalMismatch.length})\n${canonicalMismatch.length ? cap(canonicalMismatch.map(c => ${c.url} -> ${c.canonical}${c.targetInSitemap ? '' : ' (target NOT in sitemap!)'}), 100).map(s => - ${s}).join('\n') : '- none'}\n\n +
    ### Duplicate groups (${dupGroups.length})\n${dupGroups.length ? cap(dupGroups.map(g => canonical -> ${g.canonical} | dupes: ${g.alternates.join(' , ')}), 50).map(s => - ${s}).join('\n') : '- none'}\n\n +
    ### Dirty URLs\nUppercase paths: ${dirty.uppercase.length}${dirty.uppercase.length ? '\n' + cap(dirty.uppercase, 30).map(s =>   - ${s}).join('\n') : ' - none'}\nUnderscores: ${dirty.underscore.length}${dirty.underscore.length ? '\n' + cap(dirty.underscore, 30).map(s =>   - ${s}).join('\n') : ' - none'}\n\n +
    ---\nGenerated by scripts/generate-sitemaps.mjs on ${LASTMOD}. Re-run whenever content changes.\n;
  fs.writeFileSync(path.join(OUT_DIR, 'SEO-FIX-REPORT.md'), md);
}

/ ---------------------------- summary ---------------------------- /
console.log('\n========== RESULT ==========');
console.log(Seeded from old sitemaps : ${seeded.size});
console.log(Indexed URLs             : ${ok.length});
console.log(Languages                : ${langsPresent.join(', ')});
console.log(Child sitemaps           : ${indexEntries.length} -> index: ${SITE}/sitemap.xml);
console.log(lastmod (all)            : ${LASTMOD});
console.log(301 rules                : ${dedupRedirects.length} (.htaccess keeps first ${HTACCESSMAXRULES}));
console.log(Unverified (kept)        : ${unverified.length});
console.log(Output dir               : ${OUT_DIR}/);
console.log('============================\n');
if (!ok.length) { console.error('No indexable pages found - check the site is reachable / not blocking the workflow.'); process.exit(1); }

// ==================================================================
//  OTHER FILE 2 OF 2
//  Save exactly as:  scripts/gsc-submit.mjs
//  Used ONLY when you choose submittogsc = "yes" at run time.
//  Secret needed: GSCSAJSON (service-account JSON).
//  Add that service-account email as OWNER in GSC Users & permissions.
// ==================================================================
import crypto from 'node:crypto';

const saRaw = process.env.GSCSAJSON || '';
if (!saRaw) { console.log('No GSCSAJSON secret configured - skipping GSC submission.'); process.exit(0); }

let sa;
try { sa = JSON.parse(saRaw); } catch { console.error('GSCSAJSON is not valid JSON'); process.exit(1); }
if (!sa.clientemail || !sa.privatekey) { console.error('GSCSAJSON missing clientemail/privatekey'); process.exit(1); }

const site = (process.env.SITE_URL || 'https://www.egyptphotographytours.com').replace(/\/+$/, '');
const property = process.env.GSC_PROPERTY || ${site}/;
const feed = ${site}/sitemap.xml;

const b64url = b => Buffer.from(b).toString('base64url');
const now = Math.floor(Date.now() / 1000);
const head = b64url(JSON.stringify({ alg: 'RS256', typ: 'JWT' }));
const claim = b64url(JSON.stringify({
  iss: sa.client_email,
  scope: 'https://www.googleapis.com/auth/webmasters',
  aud: sa.token_uri || 'https://oauth2.googleapis.com/token',
  iat: now, exp: now + 3600,
}));
const sig = b64url(crypto.sign('RSA-SHA256', Buffer.from(${head}.${claim}), sa.private_key));

const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: new URLSearchParams({
    grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
    assertion: ${head}.${claim}.${sig},
  }),
});
const tok = await tokenRes.json();
if (!tok.access_token) { console.error('OAuth token failed:', tok); process.exit(1); }
const auth = { Authorization: Bearer ${tok.access_token} };

const put = await fetch(
  https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent(property)}/sitemaps/${encodeURIComponent(feed)},
  { method: 'PUT', headers: auth },
);
console.log(Submitted ${feed} -> HTTP ${put.status}${put.status === 200 ? ' (submitted)' : ''});
if (put.status !== 200) console.error(await put.text());

const list = await fetch(
  https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent(property)}/sitemaps,
  { headers: auth },
);
if (list.ok) {
  const data = await list.json();
  for (const s of data.sitemap || []) {
    console.log( - ${s.path} | indexed:${s.contents?.[0]?.indexed ?? '?'} submitted:${s.contents?.[0]?.submitted ?? '?'});
  }
} else {
  console.error('Could not list sitemaps:', list.status, await list.text());
}
console.log('Open GSC -> Sitemaps and watch "Indexed pages" climb.');
