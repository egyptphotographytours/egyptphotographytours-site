#!/usr/bin/env node
/*
 * fix-head-tags.cjs — SITEMAP FORGE v4 (brute-force JSON-LD edition)
 * CommonJS — works in any repo regardless of package.json "type".
 *
 * v4 upgrades:
 *   • JSON-LD cleaning is brute-force: every site URL inside every
 *     application/ld+json block gets .html stripped, looped to a fixed point.
 *   • No lookahead fragility — trailing "#fragment" and closing quotes survive.
 *   • Post-pass audit: if any ld+json block is still dirty, the file is
 *     REFUSED (never written) and the run exits with code 2 — fails loud.
 *   • Everything else identical to v3: canonical, hreflang (+zh→zh-CN),
 *     og:url, optional internal links, dry-run, backups, atomic writes,
 *     tag-count validation, machine-readable counters.
 *
 * Usage:
 *   node scripts/fix-head-tags.cjs . --dry       (report only — run first)
 *   node scripts/fix-head-tags.cjs .             (apply + backups)
 *   node scripts/fix-head-tags.cjs . --links     (also clean internal <a> links)
 */
'use strict';

var fs = require('fs');
var path = require('path');

var args = process.argv.slice(2);
var flags = args.filter(function (a) { return a.indexOf('--') === 0; });
var positional = args.filter(function (a) { return a.indexOf('--') !== 0; });
var DRY = flags.some(function (f) { return f.trim() === '--dry'; });
var LINKS = flags.some(function (f) { return f.trim() === '--links'; });
var ROOT = (positional[0] || '.').replace(/\\/g, '').trim() || '.';

var BACKUP_DIR = '.head-fix-backups';
var DOMAIN_SRC = 'https:\\/\\/www\\.egyptphotographytours\\.com';

var totals = { files: 0, changed: 0, skipped: 0, canonical: 0, hreflang: 0, zh: 0, og: 0, jsonld: 0, links: 0 };
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

/* ---------- targeted head passes (canonical + hreflang) ---------- */
function stripDotHtml(tag, counter) {
  return tag.replace(
    /(href\s*=\s*)(["'])((?:https:\/\/www\.egyptphotographytours\.com)?\/[^"']*?)\.html(?=[#?]|\2)/g,
    function (m, attr, quote, url) { counter.n++; return attr + quote + url; }
  );
}

/* ---------- v4 brute-force JSON-LD cleaner ---------- */
var LD_BLOCK_RE = /(<script nonce=""\b[^>]*type\s*=\s*["']application\/ld\+json["'][^>]*>)([\s\S]*?)(<\/script>)/gi;
var LD_DIRTY_RE = new RegExp(DOMAIN_SRC + '\\/[^"\\\\<>]*?\\.html');

function cleanJsonLdBody(body, counter) {
  var stripRe = new RegExp('(' + DOMAIN_SRC + '\\/[^"\\\\<>]*?)\\.html', 'g');
  var out = body;
  for (var guard = 0; guard < 50; guard++) {
    var c = 0;
    var next = out.replace(stripRe, function (m, url) { c++; return url; });
    if (c === 0) break;
    counter.n += c;
    out = next;
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

  /* 3) JSON-LD — brute force, fixed-point loop */
  out = out.replace(LD_BLOCK_RE, function (m, openTag, body, closeTag) {
    var c = { n: 0 };
    var fixed = cleanJsonLdBody(body, c);
    n.jsonld += c.n;
    return openTag + fixed + closeTag;
  });

  /* 4) optional: internal <a href> links */
  if (LINKS) {
    out = out.replace(
      /(<a\b[^>]*?)(href\s*=\s*)(["'])((?:https:\/\/www\.egyptphotographytours\.com)?\/[^"']*?)\.html(?=[#?]|\3)([^>]*>)/g,
      function (m, pre, attr, quote, url, post) { n.links++; return pre + attr + quote + url + post; }
    );
  }

  return { out: out, n: n };
}

/* v4 audit: refuse any file where a JSON-LD block is still dirty */
function jsonLdResidue(out) {
  var found = 0;
  out.replace(LD_BLOCK_RE, function (m, openTag, body) {
    if (LD_DIRTY_RE.test(body)) found++;
    return m;
  });
  return found;
}

/* ---------- validation: structure must be identical ---------- */
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
    console.warn('WARN: folder "' + ROOT + '" not found - falling back to "." (repo root)');
    ROOT = '.';
  }

  console.log('SITEMAP FORGE v4 - root: ' + ROOT + ' - mode: ' + (DRY ? 'DRY RUN' : 'APPLY') + (LINKS ? ' - links: yes' : ''));

  walk(ROOT, function (p) {
    totals.files++;
    var src = fs.readFileSync(p, 'utf8');
    var res = transform(src);
    var changes = res.n.canonical + res.n.hreflang + res.n.zh + res.n.og + res.n.jsonld + res.n.links;
    if (changes === 0) return;

    /* v4 refuse-not-break guard */
    var dirty = jsonLdResidue(res.out);
    if (dirty > 0) {
      totals.skipped++;
      alerts.push(p);
      report.push('REFUSED (JSON-LD residue survived - manual check needed): ' + p);
      return;
    }

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
  lines.push('SITEMAP FORGE v4 - head-tags report');
  lines.push('Mode: ' + (DRY ? 'DRY RUN (nothing written)' : 'APPLIED (backups in ' + BACKUP_DIR + '/)'));
  lines.push('Root folder: ' + ROOT);
  lines.push('Links mode: ' + (LINKS ? 'yes' : 'no'));
  lines.push('------------------------------------');
  lines.push('Scanned .html files : ' + totals.files);
  lines.push((DRY ? 'Would change       : ' : 'Changed files      : ') + totals.changed);
  lines.push('Skipped / refused   : ' + totals.skipped);
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
    version: 'v4',
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
    linksRewritten: totals.links
  }, null, 2));

  if (alerts.length > 0) {
    console.error('ATTENTION: ' + alerts.length + ' file(s) REFUSED - see REFUSED lines in the report.');
    process.exit(2);
  }
}

try {
  main();
} catch (err) {
  console.error('FATAL: ' + (err && err.stack ? err.stack : err));
  process.exit(1);
}
