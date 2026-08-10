#!/usr/bin/env python3
"""
Ultimate Smart Incremental Translation & SEO Pipeline v2
=========================================================
✅ FIXES "No translation was found" / Google blocks:
   - 3-engine fallback chain: Google → Bing → MyMemory
   - Exponential backoff + random jitter between requests
   - Repair pass: failed chunks retried after cooldown (never silently English)
✅ RESUME-SMART: skips files already translated & unchanged
✅ Self-healing: failed files saved to scripts/failed_translations.json → retried first next run
✅ BATCH PUSH: commits & pushes every 100 files
✅ GSC-SAFE SEO: canonical + hreflang + x-default injected on every file
✅ Flawless international sitemap.xml with xhtml:link tags
✅ DOM Firewall: DOCTYPE, <script>, <style>, JSON-LD protected from translation
"""

import os
import re
import sys
import json
import time
import random
import argparse
import subprocess
import concurrent.futures
from bs4 import BeautifulSoup, Comment, NavigableString, Doctype, Declaration, ProcessingInstruction
from deep_translator import GoogleTranslator
from datetime import datetime

sys.stdout.reconfigure(line_buffering=True)

# ==========================================
# CONFIGURATION
# ==========================================
DOMAIN = "https://www.egyptphotographytours.com"
BATCH_SIZE = 100                    # ✅ Push to GitHub after every 100 translated files
FAILED_MANIFEST = os.path.join('scripts', 'failed_translations.json')

TARGET_LANGS = [
    'ar', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'zh-CN', 'ko',
    'hi', 'nl', 'sv', 'pl', 'tr', 'vi', 'th', 'id', 'cs', 'ro',
    'tl', 'no', 'da', 'fi'
]

IGNORE_TAGS = {
    'script', 'style', 'code', 'pre', 'svg', 'math',
    'noscript', 'iframe', 'template', 'textarea', 'input'
}

TIMEOUT_SECONDS = 15
MAX_RETRIES = 3
CHUNK_SIZE = 4500                   # chars per chunk (Google limit is 5000 — stay safely under)
CHUNK_DELAY_MIN = 2.0               # base delay between chunks
CHUNK_DELAY_MAX = 4.5
COOLDOWN_AFTER_FAILURE = 90         # seconds to wait before repair pass
ENGINE_SWITCH_THRESHOLD = 2         # consecutive failures before switching engine

LANG_META = {
    'en':    {'flag': '🇺🇸', 'name': 'English'}, 'ar':    {'flag': '🇸🇦', 'name': 'العربية'},
    'cs':    {'flag': '🇨🇿', 'name': 'Čeština'}, 'da':    {'flag': '🇩🇰', 'name': 'Dansk'},
    'de':    {'flag': '🇩🇪', 'name': 'Deutsch'}, 'es':    {'flag': '🇪🇸', 'name': 'Español'},
    'fi':    {'flag': '🇫🇮', 'name': 'Suomi'}, 'fr':    {'flag': '🇫🇷', 'name': 'Français'},
    'hi':    {'flag': '🇮🇳', 'name': 'हिन्दी'}, 'id':    {'flag': '🇮🇩', 'name': 'Bahasa Indonesia'},
    'it':    {'flag': '🇮🇹', 'name': 'Italiano'}, 'ja':    {'flag': '🇯🇵', 'name': '日本語'},
    'ko':    {'flag': '🇰🇷', 'name': '한국어'}, 'nl':    {'flag': '🇳🇱', 'name': 'Nederlands'},
    'no':    {'flag': '🇳🇴', 'name': 'Norsk'}, 'pl':    {'flag': '🇵🇱', 'name': 'Polski'},
    'pt':    {'flag': '🇵🇹', 'name': 'Português'}, 'ro':    {'flag': '🇷🇴', 'name': 'Română'},
    'ru':    {'flag': '🇷🇺', 'name': 'Русский'}, 'sv':    {'flag': '🇸🇪', 'name': 'Svenska'},
    'th':    {'flag': '🇹🇭', 'name': 'ไทย'}, 'tl':    {'flag': '🇵🇭', 'name': 'Filipino'},
    'tr':    {'flag': '🇹🇷', 'name': 'Türkçe'}, 'vi':    {'flag': '🇻🇳', 'name': 'Tiếng Việt'},
    'zh-CN': {'flag': '🇨🇳', 'name': '中文 (简体)'}
}

# Optional Bing fallback (free, no API key) — degrades gracefully if missing
try:
    import translators as ts
    BING_AVAILABLE = True
except ImportError:
    BING_AVAILABLE = False
    print("   ⚠️ 'translators' not installed — Bing fallback disabled (pip install translators)", flush=True)

# ==========================================
# TRANSLATION ENGINE — FALLBACK CHAIN
# ==========================================
class TranslationEngine:
    """Google → Bing → MyMemory with backoff, jitter, and block detection."""

    def __init__(self):
        self.consecutive_failures = 0
        self.preferred = 'google'

    # ---- timeout wrapper ----
    @staticmethod
    def _run_with_timeout(fn, *args):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(fn, *args).result(timeout=TIMEOUT_SECONDS)

    # ---- engines ----
    def _google(self, text, target):
        return GoogleTranslator(source='en', target=target).translate(text)

    def _bing(self, text, target):
        lang = 'zh' if target == 'zh-CN' else target
        return ts.translate_text(text, translator='bing', from_language='en', to_language=lang)

    def _mymemory(self, text, target):
        from deep_translator import MyMemoryTranslator
        return MyMemoryTranslator(source='en', target=target).translate(text)

    # ---- smart dispatcher ----
    def translate(self, text, target):
        """Try engines in order. Raises if all fail."""
        engines = ['google', 'bing', 'mymemory']
        # if Google keeps failing, start with the backup
        if self.consecutive_failures >= ENGINE_SWITCH_THRESHOLD:
            engines = ['bing', 'google', 'mymemory']

        last_err = None
        for eng in engines:
            try:
                if eng == 'google':
                    result = self._run_with_timeout(self._google, text, target)
                elif eng == 'bing':
                    if not BING_AVAILABLE: continue
                    time.sleep(1)
                    result = self._run_with_timeout(self._bing, text, target)
                else:
                    if len(text) > 450: continue   # MyMemory limit
                    time.sleep(1)
                    result = self._run_with_timeout(self._mymemory, text, target)

                if result and result.strip():
                    self.consecutive_failures = 0
                    return result, eng
            except Exception as e:
                last_err = e
                continue
        self.consecutive_failures += 1
        raise RuntimeError(f"All engines failed: {last_err}")

# ==========================================
# FAILED-FILE MANIFEST (SELF-HEALING)
# ==========================================
def load_failed_manifest():
    if os.path.exists(FAILED_MANIFEST):
        try:
            with open(FAILED_MANIFEST, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()

def save_failed_manifest(failed_set):
    os.makedirs(os.path.dirname(FAILED_MANIFEST), exist_ok=True)
    with open(FAILED_MANIFEST, 'w', encoding='utf-8') as f:
        json.dump(sorted(failed_set), f, indent=2)

# ==========================================
# GIT BATCH PUSH (SAVES PROGRESS)
# ==========================================
def batch_commit_and_push(count):
    print(f"   📦 Pushing batch of {count} files to GitHub...", flush=True)
    try:
        subprocess.run(['git', 'add', '.'], check=True, capture_output=True)
        status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if status.stdout.strip():
            subprocess.run(['git', 'commit', '-m', f'🤖 Batch translation ({count} files) [skip ci]'], check=True, capture_output=True)
            subprocess.run(['git', 'pull', '--rebase', '--autostash'], capture_output=True)
            subprocess.run(['git', 'push'], check=True, capture_output=True)
            print(f"   ✅ Successfully pushed {count} files.", flush=True)
        else:
            print(f"   ℹ️ No changes to push.", flush=True)
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8') if e.stderr else str(e)
        print(f"   ⚠️ Git push warning: {err_msg}", flush=True)

# ==========================================
# URL HELPERS
# ==========================================
def get_relative_url(lang_code, base_path):
    clean = base_path.replace('index.html', '').replace('.html', '')
    if lang_code == 'en':
        return f"/{clean}" if clean else "/"
    return f"/{lang_code}/{clean}" if clean else f"/{lang_code}/"

def get_absolute_url(lang_code, base_path):
    return f"{DOMAIN}{get_relative_url(lang_code, base_path)}"

# ==========================================
# GIT CHANGE DETECTION (INCREMENTAL)
# ==========================================
def get_changed_english_files():
    try:
        result = subprocess.run(['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'], capture_output=True, text=True, check=True)
        changed = result.stdout.strip().split('\n')
        return [f for f in changed if f.endswith('.html')
                and not any(f.startswith(lang + '/') for lang in TARGET_LANGS)
                and os.path.exists(f)]
    except Exception:
        return []

def get_all_english_files():
    en_files = []
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in TARGET_LANGS and not d.startswith('.')
                   and d not in ['scripts', 'node_modules', '.github']]
        for f in files:
            if f.endswith('.html'):
                en_files.append(os.path.relpath(os.path.join(root, f), '.'))
    return en_files

# ==========================================
# DOM FIREWALL: SAFE TRANSLATION
# ==========================================
def is_translatable(text_node):
    if isinstance(text_node, (Comment, Doctype, Declaration, ProcessingInstruction)):
        return False
    if not hasattr(text_node, 'parent') or not text_node.parent or not hasattr(text_node.parent, 'name'):
        return False
    curr = text_node.parent
    while curr:
        if not hasattr(curr, 'name'): break
        if curr.name in IGNORE_TAGS: return False
        if curr.name == 'head': return False
        if curr.get('translate') == 'no': return False
        if 'notranslate' in curr.get('class', []): return False
        curr = curr.parent
    return True

def safe_translate(texts, target_lang, engine):
    """Chunk, translate with backoff + fallback, and repair failed chunks after a cooldown.
    Returns (translated_texts, had_failures)."""
    if not texts: return [], False

    # ---- build chunks by CHARACTER count ----
    chunks, current_chunk, current_len = [], [], 0
    for t in texts:
        clean_t = t.replace('\n', ' ').replace('\r', ' ').strip() or t
        add_len = len(clean_t) + 1
        if current_len + add_len > CHUNK_SIZE and current_chunk:
            chunks.append(current_chunk)
            current_chunk, current_len = [], 0
        current_chunk.append(clean_t)
        current_len += add_len
    if current_chunk: chunks.append(current_chunk)

    results = [None] * len(texts)   # filled positionally later
    failed_chunk_indices = []
    cursor = 0
    chunk_map = []                  # (chunk_index, start_position)

    for ci, chunk in enumerate(chunks):
        chunk_map.append((ci, cursor))
        cursor += len(chunk)

    def attempt_chunk(chunk):
        """Returns list of translated strings or None."""
        payload = "\n".join(chunk)
        for attempt in range(MAX_RETRIES):
            try:
                res, eng = engine.translate(payload, target_lang)
                parts = res.split("\n")
                if len(parts) == len(chunk):
                    return parts, eng
                # newline mismatch → translate one by one
                singles, ok = [], True
                for t in chunk:
                    try:
                        r, _ = engine.translate(t, target_lang)
                        singles.append(r)
                    except Exception:
                        ok = False
                        break
                    time.sleep(0.4)
                if ok: return singles, eng
            except Exception as e:
                wait = (5 * (2 ** attempt)) + random.uniform(0, 5)
                print(f"      ⚠️ Attempt {attempt+1} failed ({type(e).__name__}). Cooling {wait:.0f}s...", flush=True)
                time.sleep(wait)
        return None, None

    # ---- first pass ----
    for ci, chunk in enumerate(chunks):
        start = chunk_map[ci][1]
        print(f"      📦 Chunk {ci+1}/{len(chunks)} ({len(chunk)} strings) → {target_lang}", flush=True)
        parts, eng = attempt_chunk(chunk)
        if parts:
            for j, p in enumerate(parts):
                results[start + j] = p
            print(f"      ✅ via {eng}", flush=True)
        else:
            print(f"      ❌ Chunk {ci+1} failed — queued for repair pass", flush=True)
            failed_chunk_indices.append(ci)
        time.sleep(random.uniform(CHUNK_DELAY_MIN, CHUNK_DELAY_MAX))
        # extra breathing room every 3 chunks
        if (ci + 1) % 3 == 0:
            time.sleep(random.uniform(6, 12))

    # ---- repair pass after cooldown ----
    if failed_chunk_indices:
        print(f"      💤 Cooling {COOLDOWN_AFTER_FAILURE}s before repairing {len(failed_chunk_indices)} failed chunk(s)...", flush=True)
        time.sleep(COOLDOWN_AFTER_FAILURE)
        still_failed = []
        for ci in failed_chunk_indices:
            chunk = chunks[ci]
            start = chunk_map[ci][1]
            print(f"      🔁 Repairing chunk {ci+1}...", flush=True)
            parts, eng = attempt_chunk(chunk)
            if parts:
                for j, p in enumerate(parts):
                    results[start + j] = p
                print(f"      ✅ Repaired via {eng}", flush=True)
            else:
                still_failed.append(ci)
                # keep English so the page still renders
                for j, t in enumerate(chunk):
                    results[start + j] = t
                print(f"      ❌ Chunk {ci+1} still failing — keeping English, file queued for next run", flush=True)
            time.sleep(random.uniform(4, 7))
        if still_failed:
            return results, True

    return results, False

def extract_and_translate(soup, target_lang, engine):
    texts, nodes = [], []
    if soup.title and soup.title.string:
        texts.append(soup.title.string.strip()); nodes.append(('title', soup.title))
    for meta_name in ['description', 'og:title', 'og:description', 'twitter:title', 'twitter:description']:
        tag = soup.find('meta', attrs={'name': meta_name}) or soup.find('meta', attrs={'property': meta_name})
        if tag and tag.get('content'):
            texts.append(tag['content'].strip()); nodes.append(('meta', tag))
    for img in soup.find_all('img', alt=True):
        if img['alt'].strip() and not img['alt'].startswith('http'):
            texts.append(img['alt'].strip()); nodes.append(('alt', img))
    for text_node in soup.find_all(string=True):
        if isinstance(text_node, (Comment, Doctype, Declaration, ProcessingInstruction)): continue
        if not text_node.parent or not hasattr(text_node.parent, 'name'): continue
        if is_translatable(text_node):
            original = str(text_node).strip()
            if len(original) > 2 and not original.isspace():
                texts.append(original); nodes.append(('text', text_node))

    if not texts: return soup, False

    print(f"      🧠 Translating {len(texts)} strings...", flush=True)
    translated, had_failures = safe_translate(texts, target_lang, engine)

    if len(translated) == len(nodes):
        for i, (node_type, node) in enumerate(nodes):
            new_text = translated[i] if translated[i] else texts[i]
            if node_type == 'title': node.string = new_text
            elif node_type == 'meta': node['content'] = new_text
            elif node_type == 'alt': node['alt'] = new_text
            elif node_type == 'text': node.replace_with(NavigableString(new_text))
    return soup, had_failures

def fix_internal_links(soup, target_lang):
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith(('http', 'mailto:', 'tel:', 'javascript:', '#', '//')): continue
        if re.search(r'\.(jpg|jpeg|png|gif|svg|webp|css|js|pdf|zip|mp4|webm|ico|woff|woff2|ttf)(\?|$)', href, re.I): continue
        if any(href.startswith(f"/{lang}/") or href == f"/{lang}" for lang in TARGET_LANGS): continue
        if href.startswith('/'):
            a['href'] = f"/{target_lang}{href}" if href != '/' else f"/{target_lang}/"
        else:
            a['href'] = f"/{target_lang}/{href.replace('.html', '')}"
    return soup

def inject_dynamic_lang_menu(soup, target_lang, base_path):
    lang_menu = soup.find('div', id='lang-menu')
    if not lang_menu: return soup
    for old_link in lang_menu.find_all('a', class_='lang-item'): old_link.decompose()

    en_url = get_relative_url('en', base_path)
    en_active = "is-active" if target_lang == 'en' else ""
    lang_menu.append(BeautifulSoup(
        f'<a href="{en_url}" class="lang-item {en_active}" role="menuitem">'
        f'<span class="lang-flag" aria-hidden="true">🇺🇸</span><span class="lang-name">English</span></a>', 'lxml'))

    for lang in TARGET_LANGS:
        if os.path.exists(os.path.join(lang, base_path)):
            lang_url = get_relative_url(lang, base_path)
            is_active = "is-active" if target_lang == lang else ""
            flag, name = LANG_META[lang]['flag'], LANG_META[lang]['name']
            lang_menu.append(BeautifulSoup(
                f'<a href="{lang_url}" class="lang-item {is_active}" role="menuitem">'
                f'<span class="lang-flag" aria-hidden="true">{flag}</span><span class="lang-name">{name}</span></a>', 'lxml'))
    return soup

# ==========================================
# GLOBAL SEO & SITEMAP (GSC INDEXING GUARANTEE)
# ==========================================
def inject_global_seo_and_sitemap():
    print("\n🔗 Step 3: Injecting SEO Tags & Generating Sitemap...", flush=True)
    page_map = {}
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['scripts', 'node_modules', '.github']]
        for f in files:
            if f.endswith('.html'):
                rel = os.path.relpath(os.path.join(root, f), '.')
                base, lang_code = rel, 'en'
                for lang in TARGET_LANGS:
                    if rel.startswith(f"{lang}/"):
                        base = rel[len(f"{lang}/"):]
                        lang_code = lang
                        break
                page_map.setdefault(base, {})[lang_code] = rel

    for base, langs in page_map.items():
        for lang_code, rel_path in langs.items():
            if not os.path.exists(rel_path): continue
            with open(rel_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'lxml')

            for old in soup.find_all('link', rel='alternate'): old.decompose()
            for old in soup.find_all('link', rel='canonical'): old.decompose()
            head = soup.find('head')
            if not head: continue

            head.append(BeautifulSoup(f'<link rel="canonical" href="{get_absolute_url(lang_code, base)}" />', 'lxml'))
            for sib_lang in langs:
                hl = 'zh' if sib_lang == 'zh-CN' else sib_lang
                head.append(BeautifulSoup(
                    f'<link rel="alternate" hreflang="{hl}" href="{get_absolute_url(sib_lang, base)}" />', 'lxml'))
            head.append(BeautifulSoup(
                f'<link rel="alternate" hreflang="x-default" href="{get_absolute_url("en", base)}" />', 'lxml'))

            soup = inject_dynamic_lang_menu(soup, lang_code, base)
            with open(rel_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))

    today = datetime.now().strftime('%Y-%m-%d')
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for base, langs in page_map.items():
        for lang_code, rel_path in langs.items():
            if '404.html' in rel_path or 'sitemap.html' in rel_path: continue
            url = get_absolute_url(lang_code, base).replace(' ', '%20')
            xml.append(f'  <url>\n    <loc>{url}</loc>\n    <lastmod>{today}</lastmod>')
            for sib_lang in langs:
                hl = 'zh' if sib_lang == 'zh-CN' else sib_lang
                xml.append(f'    <xhtml:link rel="alternate" hreflang="{hl}" href="{get_absolute_url(sib_lang, base).replace(" ", "%20")}" />')
            xml.append(f'    <xhtml:link rel="alternate" hreflang="x-default" href="{get_absolute_url("en", base).replace(" ", "%20")}" />\n  </url>')
    xml.append('</urlset>')
    with open('sitemap.xml', 'w', encoding='utf-8') as f:
        f.write('\n'.join(xml))
    print("   ✅ sitemap.xml generated.", flush=True)

# ==========================================
# MAIN EXECUTION
# ==========================================
def main():
    parser = argparse.ArgumentParser(description='Smart Translation & SEO Pipeline')
    parser.add_argument('--only', help='Comma-separated filenames to process (skip everything else)')
    parser.add_argument('--force', action='store_true', help='Re-translate ALL files even if they exist')
    args = parser.parse_args()

    only_set = set(f.strip() for f in args.only.split(',')) if args.only else None

    print("=" * 60, flush=True)
    print("🚀 Smart Incremental Translation & SEO Pipeline v2", flush=True)
    print("=" * 60, flush=True)

    engine = TranslationEngine()
    failed_manifest = load_failed_manifest()
    modified_files = get_changed_english_files()
    all_en_files = get_all_english_files()

    # ✅ RESUME SMART: retry previously-failed files FIRST
    def priority(path):
        return (0 if path in failed_manifest else 1, path)
    all_en_files.sort(key=priority)

    if failed_manifest:
        print(f"   🔁 Retrying {len(failed_manifest)} previously-failed file(s) first...", flush=True)

    files_since_push = 0
    skipped = 0

    print(f"\n🌍 Step 2: Translating into {len(TARGET_LANGS)} languages (batch push every {BATCH_SIZE} files)...", flush=True)
    for rel_path in all_en_files:
        if only_set and os.path.basename(rel_path) not in only_set and rel_path not in only_set:
            continue

        needs_update = rel_path in modified_files or rel_path in failed_manifest or args.force

        with open(rel_path, 'r', encoding='utf-8') as f:
            en_soup = BeautifulSoup(f, 'lxml')

        file_had_failures = False

        for lang in TARGET_LANGS:
            trans_path = os.path.join(lang, rel_path)

            # ✅ SKIP: exists, unchanged, not failed → already done
            if os.path.exists(trans_path) and not needs_update:
                skipped += 1
                continue

            action = 'RETRY' if rel_path in failed_manifest else ('UPDATED' if os.path.exists(trans_path) else 'NEW')
            print(f"   🔄 [{action}] {rel_path} → {lang}", flush=True)

            lang_soup = BeautifulSoup(str(en_soup), 'lxml')
            lang_soup, had_failures = extract_and_translate(lang_soup, lang, engine)
            lang_soup.html['lang'] = 'zh' if lang == 'zh-CN' else lang
            lang_soup = fix_internal_links(lang_soup, lang)

            os.makedirs(os.path.dirname(trans_path), exist_ok=True)
            with open(trans_path, 'w', encoding='utf-8') as f:
                f.write(str(lang_soup))

            if had_failures:
                file_had_failures = True
            files_since_push += 1

            # ✅ PUSH EVERY 100 FILES
            if files_since_push >= BATCH_SIZE:
                batch_commit_and_push(files_since_push)
                files_since_push = 0

        # update self-healing manifest
        if file_had_failures:
            failed_manifest.add(rel_path)
            print(f"   📝 {rel_path} queued for retry next run.", flush=True)
        elif rel_path in failed_manifest:
            failed_manifest.discard(rel_path)
            print(f"   ✅ {rel_path} fully recovered!", flush=True)

    if files_since_push > 0:
        batch_commit_and_push(files_since_push)

    save_failed_manifest(failed_manifest)
    if failed_manifest:
        print(f"\n⚠️ {len(failed_manifest)} file(s) still incomplete — saved to {FAILED_MANIFEST} for next run.", flush=True)

    print(f"\n⏭️ Skipped {skipped} already-translated file/language pairs (resume mode).", flush=True)

    inject_global_seo_and_sitemap()
    print("\n🎉 Pipeline Complete!", flush=True)

if __name__ == "__main__":
    main()
