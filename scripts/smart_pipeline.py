#!/usr/bin/env python3
"""
Ultimate Smart Incremental Translation & SEO Pipeline v3.2
==========================================================
✅ DOM Firewall: Prevents <html><body> injection bugs using html.parser & new_tag()
✅ DOM Cleanup: Automatically deletes broken nested tags from previous buggy runs
✅ .html Preservation: Keeps .html extensions in canonicals and internal links
✅ Content Hashing: Only translates when actual text changes
✅ Safe Chunking: Limits to 40 strings per chunk to prevent Google Translate blocks
✅ Force Translate: Manually trigger a specific file via GitHub Actions
✅ --seo-only mode: Instantly repairs hreflang, menus & DOM WITHOUT translating
✅ Sitemap: REMOVED — handled by separate workflow
"""

import os
import re
import sys
import json
import time
import random
import hashlib
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
BATCH_SIZE = 100
FAILED_MANIFEST = os.path.join('scripts', 'failed_translations.json')
HASH_MANIFEST = os.path.join('scripts', 'translated_hashes.json')

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
CHUNK_SIZE = 2000
MAX_STRINGS_PER_CHUNK = 40
CHUNK_DELAY_MIN = 3.0
CHUNK_DELAY_MAX = 6.0
COOLDOWN_AFTER_FAILURE = 90
ENGINE_SWITCH_THRESHOLD = 2

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

try:
    import translators as ts
    BING_AVAILABLE = True
except ImportError:
    BING_AVAILABLE = False
    print("   ⚠️ 'translators' not installed — Bing fallback disabled", flush=True)

# ==========================================
# TRANSLATION ENGINE
# ==========================================
class TranslationEngine:
    def __init__(self):
        self.consecutive_failures = 0

    @staticmethod
    def _run_with_timeout(fn, *args):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(fn, *args).result(timeout=TIMEOUT_SECONDS)

    def _google(self, text, target):
        return GoogleTranslator(source='en', target=target).translate(text)

    def _bing(self, text, target):
        lang = 'zh' if target == 'zh-CN' else target
        return ts.translate_text(text, translator='bing', from_language='en', to_language=lang)

    def _mymemory(self, text, target):
        from deep_translator import MyMemoryTranslator
        return MyMemoryTranslator(source='en', target=target).translate(text)

    def translate(self, text, target):
        engines = ['google', 'bing', 'mymemory']
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
                    if len(text) > 450: continue
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
# MANIFESTS & HASHING
# ==========================================
def load_failed_manifest():
    if os.path.exists(FAILED_MANIFEST):
        try:
            with open(FAILED_MANIFEST, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except Exception: pass
    return set()

def save_failed_manifest(failed_set):
    os.makedirs(os.path.dirname(FAILED_MANIFEST), exist_ok=True)
    with open(FAILED_MANIFEST, 'w', encoding='utf-8') as f:
        json.dump(sorted(failed_set), f, indent=2)

def load_hashes():
    if os.path.exists(HASH_MANIFEST):
        try:
            with open(HASH_MANIFEST, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception: pass
    return {}

def save_hashes(hashes):
    os.makedirs(os.path.dirname(HASH_MANIFEST), exist_ok=True)
    with open(HASH_MANIFEST, 'w', encoding='utf-8') as f:
        json.dump(hashes, f, indent=2)

def get_content_hash(soup):
    texts = []
    if soup.title and soup.title.string: texts.append(soup.title.string.strip())
    for meta_name in ['description', 'og:title', 'og:description', 'twitter:title', 'twitter:description']:
        tag = soup.find('meta', attrs={'name': meta_name}) or soup.find('meta', attrs={'property': meta_name})
        if tag and tag.get('content'): texts.append(tag['content'].strip())
    for img in soup.find_all('img', alt=True):
        if img['alt'].strip() and not img['alt'].startswith('http'): texts.append(img['alt'].strip())
    for text_node in soup.find_all(string=True):
        if isinstance(text_node, (Comment, Doctype, Declaration, ProcessingInstruction)): continue
        if not text_node.parent or not hasattr(text_node.parent, 'name'): continue
        if is_translatable(text_node):
            original = str(text_node).strip()
            if len(original) > 2 and not original.isspace(): texts.append(original)
    return hashlib.md5("|".join(texts).encode('utf-8')).hexdigest()

# ==========================================
# GIT PUSH
# ==========================================
def batch_commit_and_push(count, retries=3):
    for attempt in range(retries):
        try:
            subprocess.run(['git', 'add', '.'], check=True, capture_output=True)
            status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
            if not status.stdout.strip():
                print("   ℹ️ No changes to push.", flush=True)
                return
            msg = f'🤖 Batch translation ({count} files) [skip ci]' if count > 0 else '🤖 SEO repair [skip ci]'
            subprocess.run(['git', 'commit', '-m', msg], check=True, capture_output=True)
            subprocess.run(['git', 'pull', '--rebase', '--autostash'], check=True, capture_output=True)
            subprocess.run(['git', 'push'], check=True, capture_output=True)
            print(f"   ✅ Pushed successfully.", flush=True)
            return
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode('utf-8') if e.stderr else str(e)
            print(f"   ⚠️ Push attempt {attempt+1} failed: {err}", flush=True)
            if attempt < retries - 1: time.sleep(15 * (attempt + 1))
            else: print("   ❌ Push failed after retries.", flush=True)

# ==========================================
# URL HELPERS (.html PRESERVED)
# ==========================================
def get_relative_url(lang_code, base_path):
    if base_path == 'index.html':
        clean = ''
    else:
        clean = base_path 
        
    if lang_code == 'en':
        return f"/{clean}" if clean else "/"
    return f"/{lang_code}/{clean}" if clean else f"/{lang_code}/"

def get_absolute_url(lang_code, base_path):
    return f"{DOMAIN}{get_relative_url(lang_code, base_path)}"

# ==========================================
# GIT DETECTION
# ==========================================
def get_changed_english_files():
    try:
        result = subprocess.run(['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'], capture_output=True, text=True, check=True)
        changed = result.stdout.strip().split('\n')
        return [f for f in changed if f.endswith('.html')
                and not any(f.startswith(lang + '/') for lang in TARGET_LANGS)
                and os.path.exists(f)]
    except Exception: return []

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
# DOM FIREWALL & TRANSLATION
# ==========================================
def is_translatable(text_node):
    if isinstance(text_node, (Comment, Doctype, Declaration, ProcessingInstruction)): return False
    if not hasattr(text_node, 'parent') or not text_node.parent or not hasattr(text_node.parent, 'name'): return False
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
    if not texts: return [], False
    chunks, current_chunk, current_len = [], [], 0
    for t in texts:
        clean_t = t.replace('\n', ' ').replace('\r', ' ').strip() or t
        add_len = len(clean_t) + 1
        # 🛡️ SAFE CHUNKING: Limits to 40 strings OR 2000 chars to prevent Google blocks
        if (current_len + add_len > CHUNK_SIZE or len(current_chunk) >= MAX_STRINGS_PER_CHUNK) and current_chunk:
            chunks.append(current_chunk)
            current_chunk, current_len = [], 0
        current_chunk.append(clean_t)
        current_len += add_len
    if current_chunk: chunks.append(current_chunk)

    results = [None] * len(texts)
    failed_chunk_indices = []
    chunk_map = []
    cursor = 0
    for ci, chunk in enumerate(chunks):
        chunk_map.append((ci, cursor))
        cursor += len(chunk)

    def attempt_chunk(chunk):
        payload = "\n".join(chunk)
        for attempt in range(MAX_RETRIES):
            try:
                res, eng = engine.translate(payload, target_lang)
                parts = res.split("\n")
                if len(parts) == len(chunk): return parts, eng
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

    for ci, chunk in enumerate(chunks):
        start = chunk_map[ci][1]
        print(f"      📦 Chunk {ci+1}/{len(chunks)} ({len(chunk)} strings) → {target_lang}", flush=True)
        parts, eng = attempt_chunk(chunk)
        if parts:
            for j, p in enumerate(parts): results[start + j] = p
            print(f"      ✅ via {eng}", flush=True)
        else:
            print(f"      ❌ Chunk {ci+1} failed — queued for repair pass", flush=True)
            failed_chunk_indices.append(ci)
        time.sleep(random.uniform(CHUNK_DELAY_MIN, CHUNK_DELAY_MAX))
        if (ci + 1) % 3 == 0: time.sleep(random.uniform(6, 12))

    if failed_chunk_indices:
        print(f"      💤 Cooling {COOLDOWN_AFTER_FAILURE}s before repairing {len(failed_chunk_indices)} chunk(s)...", flush=True)
        time.sleep(COOLDOWN_AFTER_FAILURE)
        still_failed = []
        for ci in failed_chunk_indices:
            chunk = chunks[ci]
            start = chunk_map[ci][1]
            print(f"      🔁 Repairing chunk {ci+1}...", flush=True)
            parts, eng = attempt_chunk(chunk)
            if parts:
                for j, p in enumerate(parts): results[start + j] = p
                print(f"      ✅ Repaired via {eng}", flush=True)
            else:
                still_failed.append(ci)
                for j, t in enumerate(chunk): results[start + j] = t
                print(f"      ❌ Chunk {ci+1} still failing — keeping English", flush=True)
            time.sleep(random.uniform(4, 7))
        if still_failed: return results, True
    return results, False

def extract_and_translate(soup, target_lang, engine):
    texts, nodes = [], []
    if soup.title and soup.title.string: texts.append(soup.title.string.strip()); nodes.append(('title', soup.title))
    for meta_name in ['description', 'og:title', 'og:description', 'twitter:title', 'twitter:description']:
        tag = soup.find('meta', attrs={'name': meta_name}) or soup.find('meta', attrs={'property': meta_name})
        if tag and tag.get('content'): texts.append(tag['content'].strip()); nodes.append(('meta', tag))
    for img in soup.find_all('img', alt=True):
        if img['alt'].strip() and not img['alt'].startswith('http'): texts.append(img['alt'].strip()); nodes.append(('alt', img))
    for text_node in soup.find_all(string=True):
        if isinstance(text_node, (Comment, Doctype, Declaration, ProcessingInstruction)): continue
        if not text_node.parent or not hasattr(text_node.parent, 'name'): continue
        if is_translatable(text_node):
            original = str(text_node).strip()
            if len(original) > 2 and not original.isspace(): texts.append(original); nodes.append(('text', text_node))

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
        
        clean_href = href.lstrip('/')
        if clean_href == 'index.html': clean_href = ''
            
        if target_lang == 'en':
            a['href'] = f"/{clean_href}" if clean_href else "/"
        else:
            a['href'] = f"/{target_lang}/{clean_href}" if clean_href else f"/{target_lang}/"
    return soup

def inject_dynamic_lang_menu(soup, target_lang, base_path):
    lang_menu = soup.find('div', id='lang-menu') or soup.find('div', class_='language-dropdown')
    if not lang_menu: return soup
    
    for old_link in lang_menu.find_all('a', class_=['lang-item', 'language-item']):
        old_link.decompose()

    en_url = get_relative_url('en', base_path)
    en_active = "is-active" if target_lang == 'en' else ""
    
    en_link_html = (
        f'<a href="{en_url}" class="lang-item language-item {en_active}" role="menuitem">'
        f'<span class="lang-flag flag-icon" aria-hidden="true">🇺🇸</span><span class="lang-name language-text">English</span></a>'
    )
    lang_menu.append(BeautifulSoup(en_link_html, 'html.parser'))

    for lang in TARGET_LANGS:
        if os.path.exists(os.path.join(lang, base_path)):
            lang_url = get_relative_url(lang, base_path)
            is_active = "is-active" if target_lang == lang else ""
            flag, name = LANG_META[lang]['flag'], LANG_META[lang]['name']
            
            lang_link_html = (
                f'<a href="{lang_url}" class="lang-item language-item {is_active}" role="menuitem">'
                f'<span class="lang-flag flag-icon" aria-hidden="true">{flag}</span><span class="lang-name language-text">{name}</span></a>'
            )
            lang_menu.append(BeautifulSoup(lang_link_html, 'html.parser'))
    return soup

# ==========================================
# GLOBAL SEO (NO SITEMAP — handled separately)
# ==========================================
def inject_global_seo():
    print("\n🔗 Injecting SEO Tags & Cleaning DOM...", flush=True)
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

    repaired = 0
    for base, langs in page_map.items():
        for lang_code, rel_path in langs.items():
            if not os.path.exists(rel_path): continue
            with open(rel_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'lxml')

            # 🧹 CLEANUP: Nuke any stray nested <html>, <head>, or <body> tags
            for nested_html in soup.find_all('html'):
                if nested_html != soup.html: nested_html.decompose()
            for nested_body in soup.find_all('body'):
                if nested_body != soup.body: nested_body.decompose()
            for nested_head in soup.find_all('head'):
                if nested_head != soup.head: nested_head.decompose()

            # ✅ Remove ALL old canonical/alternate links
            for old in soup.find_all('link', rel='alternate'): old.decompose()
            for old in soup.find_all('link', rel='canonical'): old.decompose()
            
            head = soup.find('head')
            if not head: continue

            # Inject clean canonical tag
            canon = soup.new_tag('link', rel='canonical', href=get_absolute_url(lang_code, base))
            head.append(canon)
            
            # Inject clean hreflang alternate tags
            for sib_lang in langs:
                hl = 'zh' if sib_lang == 'zh-CN' else sib_lang
                alt = soup.new_tag('link', rel='alternate', hreflang=hl, href=get_absolute_url(sib_lang, base))
                head.append(alt)
            
            # Inject x-default
            x_default = soup.new_tag('link', rel='alternate', hreflang='x-default', href=get_absolute_url("en", base))
            head.append(x_default)

            # Inject language menu
            soup = inject_dynamic_lang_menu(soup, lang_code, base)
            
            with open(rel_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            repaired += 1
    print(f"   ✅ SEO tags injected & DOM cleaned on {repaired} files.", flush=True)

# ==========================================
# MAIN EXECUTION
# ==========================================
def main():
    parser = argparse.ArgumentParser(description='Smart Translation & SEO Pipeline')
    parser.add_argument('--only', help='Comma-separated filenames to process')
    parser.add_argument('--force', action='store_true', help='Re-translate ALL files')
    parser.add_argument('--force-file', type=str, help='Force re-translate a specific file')
    parser.add_argument('--seo-only', action='store_true',
                        help='Skip translation — only repair hreflang, language menus & DOM')
    args = parser.parse_args()

    print("=" * 60, flush=True)
    print("🚀 Smart Incremental Translation & SEO Pipeline v3.2", flush=True)
    print("=" * 60, flush=True)

    if args.seo_only:
        print("🔧 SEO-ONLY REPAIR MODE — no translation will happen.", flush=True)
        inject_global_seo()
        batch_commit_and_push(0)
        print("\n🎉 Repair complete!", flush=True)
        return

    only_set = set(f.strip() for f in args.only.split(',')) if args.only else None
    engine = TranslationEngine()
    failed_manifest = load_failed_manifest()
    translated_hashes = load_hashes()
    
    modified_files = get_changed_english_files()
    all_en_files = get_all_english_files()

    all_en_files.sort(key=lambda p: (0 if p in failed_manifest else 1, p))
    if failed_manifest:
        print(f"   🔁 Retrying {len(failed_manifest)} previously-failed file(s) first...", flush=True)

    files_since_push = 0
    skipped = 0

    print(f"\n🌍 Translating into {len(TARGET_LANGS)} languages (push every {BATCH_SIZE} files)...", flush=True)

    try:
        for rel_path in all_en_files:
            is_forced = False
            if args.force_file:
                if os.path.basename(rel_path) == args.force_file or rel_path == args.force_file:
                    is_forced = True
                else: continue
            elif only_set and os.path.basename(rel_path) not in only_set and rel_path not in only_set:
                continue

            with open(rel_path, 'r', encoding='utf-8') as f:
                en_soup = BeautifulSoup(f, 'lxml')
                
            current_hash = get_content_hash(en_soup)
            saved_hash = translated_hashes.get(rel_path)

            if saved_hash is None:
                all_exist = all(os.path.exists(os.path.join(lang, rel_path)) for lang in TARGET_LANGS)
                if all_exist and not args.force and not is_forced:
                    translated_hashes[rel_path] = current_hash
                    skipped += len(TARGET_LANGS)
                    continue

            content_changed = (current_hash != saved_hash)
            needs_update = rel_path in modified_files or rel_path in failed_manifest or args.force
            file_had_failures = False
            
            if not content_changed and not args.force and not is_forced and rel_path not in failed_manifest:
                translated_hashes[rel_path] = current_hash
                skipped += len(TARGET_LANGS)
                continue

            for lang in TARGET_LANGS:
                trans_path = os.path.join(lang, rel_path)

                if os.path.exists(trans_path) and not content_changed and not needs_update and not is_forced:
                    skipped += 1
                    continue

                action = 'RETRY' if rel_path in failed_manifest else ('UPDATED' if os.path.exists(trans_path) else 'NEW')
                if is_forced: action = 'FORCED'
                print(f"   🔄 [{action}] {rel_path} → {lang}", flush=True)

                lang_soup = BeautifulSoup(str(en_soup), 'lxml')
                lang_soup, had_failures = extract_and_translate(lang_soup, lang, engine)
                lang_soup.html['lang'] = 'zh' if lang == 'zh-CN' else lang
                lang_soup = fix_internal_links(lang_soup, lang)

                os.makedirs(os.path.dirname(trans_path), exist_ok=True)
                with open(trans_path, 'w', encoding='utf-8') as f:
                    f.write(str(lang_soup))

                if had_failures: file_had_failures = True
                files_since_push += 1

                if files_since_push >= BATCH_SIZE:
                    save_hashes(translated_hashes)
                    batch_commit_and_push(files_since_push)
                    files_since_push = 0

            if file_had_failures:
                failed_manifest.add(rel_path)
                print(f"   📝 {rel_path} queued for retry next run.", flush=True)
            elif rel_path in failed_manifest:
                failed_manifest.discard(rel_path)
                print(f"   ✅ {rel_path} fully recovered!", flush=True)
                translated_hashes[rel_path] = current_hash
            else:
                translated_hashes[rel_path] = current_hash

    except KeyboardInterrupt:
        print("\n⚠️ Interrupted — saving progress...", flush=True)

    finally:
        save_failed_manifest(failed_manifest)
        save_hashes(translated_hashes)
        
        if files_since_push > 0:
            batch_commit_and_push(files_since_push)
        print("\n🔒 Final safety step: injecting SEO, hreflang & language menus...", flush=True)
        inject_global_seo()

    if failed_manifest:
        print(f"\n⚠️ {len(failed_manifest)} file(s) still incomplete — will retry next run.", flush=True)
    print(f"⏭️ Skipped {skipped} already-translated file/language pairs (resume mode).", flush=True)
    print("\n🎉 Pipeline Complete!", flush=True)

if __name__ == "__main__":
    main()
