#!/usr/bin/env node
/*
 * fix-head-tags.cjs — SITEMAP FORGE v6 (SAFE DEEP CLEAN)
 * CommonJS — works in any repo regardless of package.json "type".
 *
 * Removes every .html remnant of egyptphotographytours.com URLs from:
 *   • <link rel="canonical"> and all hreflang alternates (+ zh -> zh-CN)
 *   • <meta property="og:url">
 *   • ALL application/ld+json blocks (absolute AND root-relative URLs),
 *     cleaned with a fixed-point loop
 *   • optional --links: internal <a href> links
 *
 * SAFETY LAYERS (a file is written only if ALL pass):
 *   1. something actually matched
 *   2. residue re-scan of every ld+json block = zero
 *   3. link/meta/script/hreflang/canonical tag counts unchanged
 *   4. every ld+json block still passes JSON.parse after cleaning
 *   5. </html> still present (document structure intact)
 *   Failing any layer = file REFUSED and left untouched.
 *   Originals are backed up; writes are atomic (temp file + rename).
 *
 * Usage:
 *   node scripts/fix-head-tags.cjs . --dry
 *   node scripts/fix-head-tags.cjs .
 *   node scripts/fix-head-tags.cjs . --links
 *
 * Exit codes: 0 ok · 1 fatal error · 2 refused files present
 */
'use strict';

var fs = require('fs');
var path = require('path');

var args = process.argv.slice(2);
var DRY = args.some(function (a) { return a.trim() === '--dry'; });
var LINKS = args.some(function (a) { return a.trim() === '--links'; });
var positional = args.filter(function (a) { return a.indexOf('--') !== 0; });
var ROOT = (positional[0] || '.').replace(/\\/g, '').trim() || '.';

var BACKUP_DIR = '.head-fix-backups';
var DOMAIN_SRC = 'https:\\/\\/www\\.egyptphotographytours\\.com';

var totals = { files: 0, changed: 0, skipped: 0, canonical: 0, hreflang: 0, zh: 0, og: 0, jsonld: 0, links: 0, jsonBrokenBefore: 0 };
var report = [];
var alerts = [];

function walk(dir, cb) {
  var entries = fs.readdirSync(dir, { withFileTypes: true });
  for (var i = 0; i < entries.length; i++) {
    var e = entries[i];
    var p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === 'node_modules' || e.name === '.git' || e.name === BACKUP_DIR) continue;
      walk(p, cb);
    } else if (e.name.length > 5 && e.name.slice(-5) === '.html') {
      cb(p);
    }
  }
}

function countRe(s, re) { return (s.match(re) || []).length; }
function tryParse(s) { try { JSON.parse(s); return true; } catch (e) { return false; } }

/* ---------- ld+json helpers ---------- */
var LD_BLOCK_SRC = '(<script nonce=""\\b[^>]*type\\s*=\\s*["\']application\\/ld\\+json["\'][^>]*>)([\\s\\S]*?)(<\\/script>)';
var LD_BLOCK_RE = new RegExp(LD_BLOCK_SRC, 'gi');
var LD_DIRTY_RE = new RegExp(DOMAIN_SRC + '\\/[^"\\\\<>]*?\\.html');

function collectLdBodies(html) {
  var out = [];
  var re = new RegExp(LD_BLOCK_SRC, 'gi');
  var m;
  while ((m = re.exec(html)) !== null) out.push(m[2]);
  return out;
}

/* ---------- head-tag cleaning ---------- */
function stripDotHtml(tag, counter) {
  return tag.replace(
    /(href\s*=\s*)(["'])((?:https:\/\/www\.egyptphotographytours\.com)?\/[^"']*?)\.html(?=[#?]|\2)/g,
    function (m, attr, quote, url) { counter.n++; return attr + quote + url; }
  );
}

/* ---------- v6 two-pass brute-force schema cleaner ---------- */
function cleanJsonLdBody(body, counter) {
  var out = body;
  /* pass 1: absolute site URLs — fixed-point loop */
  var absRe = new RegExp('(' + DOMAIN_SRC + '\\/[^"\\\\<>]*?)\\.html', 'g');
  for (var g1 = 0; g1 < 50; g1++) {
    var c1 = 0;
    var next1 = out.replace(absRe, function (m, url) { c1++; return url; });
    if (c1 === 0) break;
    counter.n += c1;
    out = next1;
  }
  /* pass 2: root-relative path strings like "/resources.html" */
  var relRe = /"(\/[a-z0-9][a-z0-9\-\/]*?)\.html"/g;
  for (var g2 = 0; g2 < 50; g2++) {
    var c2 = 0;
    var next2 = out.replace(relRe, function (m, p) { c2++; return '"' + p + '"'; });
    if (c2 === 0) break;
    counter.n += c2;
    out = next2;
  }
  return out;
}

function transform(src) {
  var n = { canonical: 0, hreflang: 0, zh: 0, og: 0, jsonld: 0, links: 0 };
  var out = src;

  /* 1) canonical + hreflang alternates */
  out = out.replace(/<link\b[^>]*>/g, function (tag) {
    if (!/rel\s*=\s*["'](canonical|alternate)["']/.test(tag)) return tag;
    var t = tag;
    var c = { n: 0 };
    t = stripDotHtml(t, c);
    if (c.n > 0) {
      if (/hreflang/.test(t)) n.hreflang += c.n; else n.canonical += c.n;
    }
    if (/hreflang\s*=\s*["']zh["']/.test(t)) {
      t = t.replace(/hreflang\s*=\s*["']zh["']/g, 'hreflang="zh-CN"');
      n.zh++;
    }
    return t;
  });

  /* 2) og:url */
  out = out.replace(/<meta\b[^>]*>/g, function (tag) {
    if (!/property\s*=\s*["']og:url["']/.test(tag)) return tag;
    var c = { n: 0 };
    var t = tag.replace(
      /(content\s*=\s*)(["'])((?:https:\/\/www\.egyptphotographytours\.com)?\/[^"']*?)\.html(?=[#?]|\2)/g,
      function (m, attr, quote, url) { c.n++; return attr + quote + url; }
    );
    n.og += c.n;
    return t;
  });

  /* 3) every ld+json block — brute force, fixed point */
  out = out.replace(new RegExp(LD_BLOCK_SRC, 'gi'), function (m, openTag, body, closeTag) {
    var c = { n: 0 };
    var fixed = cleanJsonLdBody(body, c);
    n.jsonld += c.n;
    return openTag + fixed + closeTag;
  });

  /* 4) optional internal <a href> links */
  if (LINKS) {
    out = out.replace(
      /(<a\b[^>]*?)(href\s*=\s*)(["'])((?:https:\/\/www\.egyptphotographytours\.com)?\/[^"']*?)\.html(?=[#?]|\3)([^>]*>)/g,
      function (m, pre, attr, quote, url, post) { n.links++; return pre + attr + quote + url + post; }
    );
  }

  return { out: out, n: n };
}

/* ---------- v6 deep validation ---------- */
function jsonLdResidue(out) {
  var found = 0;
  out.replace(new RegExp(LD_BLOCK_SRC, 'gi'), function (m, openTag, body) {
    if (LD_DIRTY_RE.test(body)) found++;
    return m;
  });
  return found;
}

function deepValidate(before, after) {
  if (countRe(before, /<link\b/g) !== countRe(after, /<link\b/g)) return 'link tag count changed';
  if (countRe(before, /<meta\b/g) !== countRe(after, /<meta\b/g)) return 'meta tag count changed';
  if (countRe(before, /<script nonce=""\b/g) !== countRe(after, /<script nonce=""\b/g)) return 'script tag count changed';
  if (countRe(before, /hreflang\s*=/g) !== countRe(after, /hreflang\s*=/g)) return 'hreflang count changed';
  if (countRe(before, /rel\s*=\s*["']canonical/g) !== countRe(after, /rel\s*=\s*["']canonical/g)) return 'canonical count changed';
  if (after.indexOf('</html>') === -1) return 'document structure lost (</html> missing)';
  var bodies = collectLdBodies(after);
  for (var i = 0; i < bodies.length; i++) {
    if (!tryParse(bodies[i])) return 'JSON-LD block failed JSON.parse after cleaning';
  }
  return null;
}

function flatName(p) { return p.replace(/[\\\/]/g, '__'); }

function main() {
  if (!fs.existsSync(ROOT)) {
    console.warn('WARN: folder "' + ROOT + '" not found - falling back to "." (repo root)');
    ROOT = '.';
  }

  console.log('SITEMAP FORGE v6 SAFE DEEP CLEAN - root: ' + ROOT + ' - mode: ' + (DRY ? 'DRY RUN' : 'APPLY') + (LINKS ? ' - links: yes' : ''));

  walk(ROOT, function (p) {
    totals.files++;
    var src = fs.readFileSync(p, 'utf8');

    /* pre-existing JSON health note (informational) */
    var preBodies = collectLdBodies(src);
    var preBroken = 0;
    preBodies.forEach(function (b) { if (!tryParse(b)) preBroken++; });
    if (preBroken > 0) {
      totals.jsonBrokenBefore += preBroken;
      report.push('NOTE (pre-existing invalid JSON-LD, regex-clean only): ' + p);
    }

    var res = transform(src);
    var changes = res.n.canonical + res.n.hreflang + res.n.zh + res.n.og + res.n.jsonld + res.n.links;
    if (changes === 0) return;

    /* safety layer: zero residue */
    var dirty = jsonLdResidue(res.out);
    if (dirty > 0) {
      totals.skipped++;
      alerts.push(p);
      report.push('REFUSED (residue survived): ' + p);
      return;
    }

    /* safety layers: tags + JSON.parse + structure */
    var problem = deepValidate(src, res.out);
    if (problem) {
      totals.skipped++;
      alerts.push(p);
      report.push('REFUSED (' + problem + '): ' + p);
      return;
    }

    totals.changed++;
    totals.canonical += res.n.canonical;
    totals.hreflang += res.n.hreflang;
    totals.zh += res.n.zh;
    totals.og += res.n.og;
    totals.jsonld += res.n.jsonld;
    totals.links += res.n.links;
    report.push((DRY ? 'WOULD FIX' : 'FIXED') + ' (' + changes + ' tags, jsonld:' + res.n.jsonld + '): ' + p);

    if (!DRY) {
      if (!fs.existsSync(BACKUP_DIR)) fs.mkdirSync(BACKUP_DIR, { recursive: true });
      fs.writeFileSync(path.join(BACKUP_DIR, flatName(p) + '.bak'), src);
      var tmp = p + '.tmp';
      fs.writeFileSync(tmp, res.out);
      fs.renameSync(tmp, p);
    }
  });

  var lines = [];
  lines.push('SITEMAP FORGE v6 - SAFE DEEP CLEAN report');
  lines.push('Mode: ' + (DRY ? 'DRY RUN (nothing written)' : 'APPLIED (backups in ' + BACKUP_DIR + '/)'));
  lines.push('Root folder: ' + ROOT);
  lines.push('Links mode: ' + (LINKS ? 'yes' : 'no'));
  lines.push('------------------------------------');
  lines.push('Scanned .html files      : ' + totals.files);
  lines.push((DRY ? 'Would change            : ' : 'Changed files           : ') + totals.changed);
  lines.push('Skipped / refused        : ' + totals.skipped);
  lines.push('canonical rewrites       : ' + totals.canonical);
  lines.push('hreflang rewrites        : ' + totals.hreflang);
  lines.push('zh -> zh-CN fixes        : ' + totals.zh);
  lines.push('og:url rewrites          : ' + totals.og);
  lines.push('JSON-LD URL fixes        : ' + totals.jsonld);
  lines.push('internal <a> link fixes  : ' + totals.links);
  lines.push('pre-existing bad JSON-LD : ' + totals.jsonBrokenBefore + ' block(s) (flagged, regex-cleaned only)');
  lines.push('------------------------------------');
  lines.push(report.join('\n'));
  var text = lines.join('\n');
  console.log(text);

  fs.writeFileSync('head-fix-report.txt', text);
  fs.writeFileSync('head-fix-changed.txt', String(totals.changed));
  fs.writeFileSync('head-fix-summary.json', JSON.stringify({
    version: 'v6-safe-deep-clean',
    mode: DRY ? 'dry-run' : 'apply',
    links: LINKS,
    root: ROOT,
    files: totals.files,
    changed: totals.changed,
    skipped: totals.skipped,
    refused: alerts.length,
    canonical: totals.canonical,
    hreflang: totals.hreflang,
    zhToZhCN: totals.zh,
    ogUrl: totals.og,
    jsonld: totals.jsonld,
    linksRewritten: totals.links,
    jsonBrokenBefore: totals.jsonBrokenBefore
  }, null, 2));

  if (alerts.length > 0) {
    console.error('ATTENTION: ' + alerts.length + ' file(s) REFUSED by the safety gates - see report.');
    process.exit(2);
  }
}

try {
  main();
} catch (err) {
  console.error('FATAL: ' + (err && err.stack ? err.stack : err));
  process.exit(1);
}
