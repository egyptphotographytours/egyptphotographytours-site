#!/usr/bin/env node
/*
 * purify-schema.cjs — STRUCTURED DATA PURIFIER (JSON-aware engine)
 * CommonJS — works in any repo regardless of package.json "type".
 *
 * SCOPE: application/ld+json blocks ONLY. Nothing else is ever touched.
 *
 * ENGINE:
 *   1. Extract every ld+json block.
 *   2. JSON.parse it → recursively walk ALL string values →
 *      strip ".html" from every egyptphotographytours.com URL
 *      (absolute and root-relative) → rebuild with JSON.stringify.
 *   3. Blocks that fail JSON.parse get a brute-force regex sweep instead.
 *
 * SAFETY (file is written only if ALL pass):
 *   - at least one URL actually changed
 *   - every rebuilt block still passes JSON.parse
 *   - zero ".html" site-URL residue in any block
 *   - script/link/meta tag counts unchanged
 *   - </html> still present
 *   Otherwise the file is REFUSED and left untouched.
 *   Backups + atomic writes + dry-run + machine-readable counters.
 *
 * Usage:
 *   node scripts/purify-schema.cjs . --dry
 *   node scripts/purify-schema.cjs .
 *
 * Exit codes: 0 ok · 1 fatal · 2 refused files present
 */
'use strict';

var fs = require('fs');
var path = require('path');

var args = process.argv.slice(2);
var DRY = args.some(function (a) { return a.trim() === '--dry'; });
var positional = args.filter(function (a) { return a.indexOf('--') !== 0; });
var ROOT = (positional[0] || '.').replace(/\\/g, '').trim() || '.';

var BACKUP_DIR = '.schema-purify-backups';
var DOMAIN = 'https://www.egyptphotographytours.com';

var totals = {
  files: 0, changed: 0, skipped: 0, refused: 0,
  blocks: 0, blocksPurged: 0, urlsFixed: 0,
  parseFailBlocks: 0, fallbackBlocks: 0
};
var report = [];
var alerts = [];

var LD_BLOCK_SRC = '(<script nonce=""\\b[^>]*type\\s*=\\s*["\']application\\/ld\\+json["\'][^>]*>)([\\s\\S]*?)(<\\/script>)';

function walkDir(dir, cb) {
  var entries = fs.readdirSync(dir, { withFileTypes: true });
  for (var i = 0; i < entries.length; i++) {
    var e = entries[i];
    var p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === 'node_modules' || e.name === '.git' || e.name === BACKUP_DIR) continue;
      walkDir(p, cb);
    } else if (e.name.length > 5 && e.name.slice(-5) === '.html') {
      cb(p);
    }
  }
}

function countRe(s, re) { return (s.match(re) || []).length; }
function tryParse(s) { try { JSON.parse(s); return true; } catch (e) { return false; } }

/* ---------- value-level cleaning ---------- */
var ABS_RE = /(https:\/\/www\.egyptphotographytours\.com\/[^\s"#?]*?)\.html(?=[#?\s]|$)/g;
var REL_FULL_RE = /^(\/[a-z0-9][a-z0-9\-\/]*)\.html$/;

function cleanString(s, counter) {
  var out = s.replace(ABS_RE, function (m, url) { counter.n++; return url; });
  var rel = out.match(REL_FULL_RE);
  if (rel) { counter.n++; out = rel[1]; }
  return out;
}

function walkValue(v, counter) {
  if (typeof v === 'string') return cleanString(v, counter);
  if (Array.isArray(v)) {
    return v.map(function (x) { return walkValue(x, counter); });
  }
  if (v && typeof v === 'object') {
    var out = {};
    Object.keys(v).forEach(function (k) { out[k] = walkValue(v[k], counter); });
    return out;
  }
  return v;
}

/* ---------- regex fallback for unparseable blocks ---------- */
function regexSweep(body, counter) {
  var out = body;
  var absRe = new RegExp('(https:\\/\\/www\\.egyptphotographytours\\.com\\/[^"\\\\<>]*?)\\.html', 'g');
  for (var g1 = 0; g1 < 50; g1++) {
    var c1 = 0;
    var next1 = out.replace(absRe, function (m, url) { c1++; return url; });
    if (c1 === 0) break;
    counter.n += c1;
    out = next1;
  }
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

/* ---------- block purifier ---------- */
function purifyBlock(body, stats) {
  stats.blocks++;
  var data = null;
  try { data = JSON.parse(body); } catch (e) { data = null; }

  if (data !== null) {
    var counter = { n: 0 };
    var cleaned = walkValue(data, counter);
    if (counter.n > 0) {
      stats.urls += counter.n;
      stats.purged++;
      return { body: JSON.stringify(cleaned, null, 1), changed: true };
    }
    return { body: body, changed: false };
  }

  /* invalid JSON → regex fallback */
  stats.parseFail++;
  var counter2 = { n: 0 };
  var swept = regexSweep(body, counter2);
  if (counter2.n > 0) {
    stats.urls += counter2.n;
    stats.purged++;
    stats.fallback++;
    return { body: swept, changed: true };
  }
  return { body: body, changed: false };
}

/* ---------- file-level transform ---------- */
function purifyFile(src, stats) {
  var out = src.replace(new RegExp(LD_BLOCK_SRC, 'gi'), function (m, openTag, body, closeTag) {
    var r = purifyBlock(body, stats);
    return openTag + r.body + closeTag;
  });
  return out;
}

/* ---------- safety gates ---------- */
function postValidate(before, after) {
  if (countRe(before, /<script nonce=""\b/g) !== countRe(after, /<script nonce=""\b/g)) return 'script tag count changed';
  if (countRe(before, /<link\b/g) !== countRe(after, /<link\b/g)) return 'link tag count changed';
  if (countRe(before, /<meta\b/g) !== countRe(after, /<meta\b/g)) return 'meta tag count changed';
  if (after.indexOf('</html>') === -1) return 'document structure lost (</html> missing)';
  var re = new RegExp(LD_BLOCK_SRC, 'gi');
  var m;
  while ((m = re.exec(after)) !== null) {
    var body = m[2];
    if (!tryParse(body)) return 'JSON-LD block failed JSON.parse after purify';
    if (/egyptphotographytours\.com\/[^"]*?\.html/.test(body)) return 'absolute .html residue survived';
    if (/"(\/[a-z0-9][a-z0-9\-\/]*?)\.html"/.test(body)) return 'root-relative .html residue survived';
  }
  return null;
}

function flatName(p) { return p.replace(/[\\\/]/g, '__'); }

/* ---------- main ---------- */
function main() {
  if (!fs.existsSync(ROOT)) {
    console.warn('WARN: folder "' + ROOT + '" not found - falling back to "." (repo root)');
    ROOT = '.';
  }

  console.log('STRUCTURED DATA PURIFIER (JSON-aware) - root: ' + ROOT + ' - mode: ' + (DRY ? 'DRY RUN' : 'APPLY'));

  walkDir(ROOT, function (p) {
    totals.files++;
    var src = fs.readFileSync(p, 'utf8');
    var stats = { blocks: 0, purged: 0, urls: 0, parseFail: 0, fallback: 0 };
    var out = purifyFile(src, stats);

    totals.blocks += stats.blocks;
    totals.parseFailBlocks += stats.parseFail;
    totals.fallbackBlocks += stats.fallback;

    if (stats.urls === 0) return;

    var problem = postValidate(src, out);
    if (problem) {
      totals.refused++;
      alerts.push(p);
      report.push('REFUSED (' + problem + '): ' + p);
      return;
    }

    totals.changed++;
    totals.blocksPurged += stats.purged;
    totals.urlsFixed += stats.urls;
    report.push((DRY ? 'WOULD PURIFY' : 'PURIFIED') + ' (' + stats.urls + ' URLs in ' + stats.purged + ' blocks' + (stats.fallback > 0 ? ', regex-fallback:' + stats.fallback : '') + '): ' + p);

    if (!DRY) {
      if (!fs.existsSync(BACKUP_DIR)) fs.mkdirSync(BACKUP_DIR, { recursive: true });
      fs.writeFileSync(path.join(BACKUP_DIR, flatName(p) + '.bak'), src);
      var tmp = p + '.tmp';
      fs.writeFileSync(tmp, out);
      fs.renameSync(tmp, p);
    }
  });

  var lines = [];
  lines.push('STRUCTURED DATA PURIFIER - report (JSON-aware engine)');
  lines.push('Mode: ' + (DRY ? 'DRY RUN (nothing written)' : 'APPLIED (backups in ' + BACKUP_DIR + '/)'));
  lines.push('Root folder: ' + ROOT);
  lines.push('------------------------------------');
  lines.push('Scanned .html files   : ' + totals.files);
  lines.push((DRY ? 'Would purify         : ' : 'Purified files       : ') + totals.changed);
  lines.push('Refused (safety gate) : ' + totals.refused);
  lines.push('ld+json blocks seen   : ' + totals.blocks);
  lines.push('Blocks purified       : ' + totals.blocksPurged);
  lines.push('URLs fixed            : ' + totals.urlsFixed);
  lines.push('Unparseable blocks    : ' + totals.parseFailBlocks + ' (regex fallback: ' + totals.fallbackBlocks + ')');
  lines.push('------------------------------------');
  lines.push(report.join('\n'));
  var text = lines.join('\n');
  console.log(text);

  fs.writeFileSync('schema-purify-report.txt', text);
  fs.writeFileSync('schema-purify-changed.txt', String(totals.changed));
  fs.writeFileSync('schema-purify-summary.json', JSON.stringify({
    engine: 'structured-data-purifier-json-aware',
    mode: DRY ? 'dry-run' : 'apply',
    root: ROOT,
    files: totals.files,
    changed: totals.changed,
    refused: totals.refused,
    blocks: totals.blocks,
    blocksPurged: totals.blocksPurged,
    urlsFixed: totals.urlsFixed,
    parseFailBlocks: totals.parseFailBlocks,
    fallbackBlocks: totals.fallbackBlocks
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
