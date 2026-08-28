#!/usr/bin/env node
/*
 * fix-head-tags.cjs — SITEMAP FORGE v3 head-tag cleaner (CommonJS build)
 * Works in any repo regardless of package.json "type".
 *
 * Rewrites on every .html page of YOUR domain only:
 *   • <link rel="canonical">            → clean URL
 *   • <link rel="alternate" hreflang>   → clean URL  +  hreflang "zh" → "zh-CN"
 *   • <meta property="og:url">          → clean URL
 *   • JSON-LD "url" / "@id" / crumbs    → clean URL (keeps #fragments)
 *   • optional --links: internal <a href> links → clean URL
 *
 * v3: machine-readable counters (head-fix-changed.txt, head-fix-summary.json),
 *     fatal errors exit non-zero, everything else identical & idempotent.
 *
 * Usage:
 *   node scripts/fix-head-tags.cjs . --dry
 *   node scripts/fix-head-tags.cjs .
 *   node scripts/fix-head-tags.cjs . --links
 */
'use strict';

var fs = require('fs');
var path = require('path');

var args = process.argv.slice(2);
var flags = args.filter(function (a) { return a.indexOf('--') === 0; });
var positional = args.filter(function (a) { return a.indexOf('--') !== 0; });
var DRY = flags.indexOf('--dry') !== -1;
var LINKS = flags.indexOf('--links') !== -1;
var ROOT = positional[0] || '.';

ROOT = String(ROOT).replace(/\\/g, '').trim();
if (ROOT === '') ROOT = '.';

var BACKUP_DIR = '.head-fix-backups';

var totals = { files: 0, changed: 0, skipped: 0, canonical: 0, hreflang: 0, zh: 0, og: 0, jsonld: 0, links: 0 };
var report = [];

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

function stripDotHtml(tag, counter) {
  return tag.replace(
    /(href\s*=\s*)(["'])((?:https:\/\/www\.egyptphotographytours\.com)?\/[^"']*?)\.html(?=[#?]|\2)/g,
    function (m, attr, quote, url) { counter.n++; return attr + quote + url; }
  );
}

function transform(src) {
  var n = { canonical: 0, hreflang: 0, zh: 0, og: 0, jsonld: 0, links: 0 };
  var out = src;

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

  out = out.replace(
    /(<script nonce=""\b[^>]*type\s*=\s*["']application\/ld\+json["'][^>]*>)([\s\S]*?)(<\/script>)/g,
    function (m, openTag, body, closeTag) {
      var c = 0;
      var fixed = body.replace(
        /(https:\/\/www\.egyptphotographytours\.com\/[^"\\]*?)\.html(?=[#"])/g,
        function (mm, url) { c++; return url; }
      );
      n.jsonld += c;
      return openTag + fixed + closeTag;
    }
  );

  if (LINKS) {
    out = out.replace(
      /(<a\b[^>]*?)(href\s*=\s*)(["'])((?:https:\/\/www\.egyptphotographytours\.com)?\/[^"']*?)\.html(?=[#?]|\3)([^>]*>)/g,
      function (m, pre, attr, quote, url, post) { n.links++; return pre + attr + quote + url + post; }
    );
  }

  return { out: out, n: n };
}

function validate(before, after) {
  if (countRe(before, /<link\b/g) !== countRe(after, /<link\b/g)) return 'link tag count changed';
  if (countRe(before, /<meta\b/g) !== countRe(after, /<meta\b/g)) return 'meta tag count changed';
  if (countRe(before, /<script nonce=""\b/g) !== countRe(after, /<script nonce=""\b/g)) return 'script tag count changed';
  if (countRe(before, /hreflang\s*=/g) !== countRe(after, /hreflang\s*=/g)) return 'hreflang count changed';
  if (countRe(before, /rel\s*=\s*["']canonical/g) !== countRe(after, /rel\s*=\s*["']canonical/g)) return 'canonical count changed';
  return null;
}

function flatName(p) { return p.replace(/[\\\/]/g, '__'); }

function main() {
  if (!fs.existsSync(ROOT)) {
    console.warn('WARN: folder "' + ROOT + '" not found — falling back to "." (repo root)');
    ROOT = '.';
  }

  console.log('SITEMAP FORGE v3 · root: ' + ROOT + ' · mode: ' + (DRY ? 'DRY RUN' : 'APPLY') + (LINKS ? ' · links: yes' : ''));

  walk(ROOT, function (p) {
    totals.files++;
    var src = fs.readFileSync(p, 'utf8');
    var res = transform(src);
    var changes = res.n.canonical + res.n.hreflang + res.n.zh + res.n.og + res.n.jsonld + res.n.links;
    if (changes === 0) return;

    var problem = validate(src, res.out);
    if (problem) {
      totals.skipped++;
      report.push('SKIPPED (' + problem + '): ' + p);
      return;
    }

    totals.changed++;
    totals.canonical += res.n.canonical;
    totals.hreflang += res.n.hreflang;
    totals.zh += res.n.zh;
    totals.og += res.n.og;
    totals.jsonld += res.n.jsonld;
    totals.links += res.n.links;
    report.push((DRY ? 'WOULD FIX' : 'FIXED') + ' (' + changes + ' tags): ' + p);

    if (!DRY) {
      if (!fs.existsSync(BACKUP_DIR)) fs.mkdirSync(BACKUP_DIR, { recursive: true });
      fs.writeFileSync(path.join(BACKUP_DIR, flatName(p) + '.bak'), src);
      var tmp = p + '.tmp';
      fs.writeFileSync(tmp, res.out);
      fs.renameSync(tmp, p);
    }
  });

  var lines = [];
  lines.push('SITEMAP FORGE v3 — head-tags report');
  lines.push('Mode: ' + (DRY ? 'DRY RUN (nothing written)' : 'APPLIED (backups in ' + BACKUP_DIR + '/)'));
  lines.push('Root folder: ' + ROOT);
  lines.push('Links mode: ' + (LINKS ? 'yes' : 'no'));
  lines.push('------------------------------------');
  lines.push('Scanned .html files : ' + totals.files);
  lines.push((DRY ? 'Would change       : ' : 'Changed files      : ') + totals.changed);
  lines.push('Skipped (protected) : ' + totals.skipped);
  lines.push('canonical rewrites  : ' + totals.canonical);
  lines.push('hreflang rewrites   : ' + totals.hreflang);
  lines.push('zh -> zh-CN fixes   : ' + totals.zh);
  lines.push('og:url rewrites     : ' + totals.og);
  lines.push('JSON-LD URL fixes   : ' + totals.jsonld);
  lines.push('internal <a> links  : ' + totals.links);
  lines.push('------------------------------------');
  lines.push(report.join('\n'));
  var text = lines.join('\n');
  console.log(text);

  fs.writeFileSync('head-fix-report.txt', text);
  fs.writeFileSync('head-fix-changed.txt', String(totals.changed));
  fs.writeFileSync('head-fix-summary.json', JSON.stringify({
    mode: DRY ? 'dry-run' : 'apply',
    links: LINKS,
    root: ROOT,
    files: totals.files,
    changed: totals.changed,
    skipped: totals.skipped,
    canonical: totals.canonical,
    hreflang: totals.hreflang,
    zhToZhCN: totals.zh,
    ogUrl: totals.og,
    jsonld: totals.jsonld,
    linksRewritten: totals.links
  }, null, 2));
}

try {
  main();
} catch (err) {
  console.error('FATAL: ' + (err && err.stack ? err.stack : err));
  process.exit(1);
}
