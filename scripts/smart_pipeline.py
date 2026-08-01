#!/usr/bin/env python3
"""
Smart Incremental Translation & SEO Pipeline
=============================================
- Translates ONLY new or changed English files (incremental)
- DOM Firewall: Never translates <script>, <style>, JSON-LD
- Smart Dynamic Menu: Rebuilds language dropdown so users can switch back to English
- 15-second timeout kill-switch to prevent Google Translate from hanging
- Injects perfect canonical + hreflang tags based on what actually exists
- Generates flawless international sitemap.xml with xhtml:link tags
"""

import os
import re
import sys
import time
import subprocess
import concurrent.futures
from bs4 import BeautifulSoup, Comment, NavigableString
from deep_translator import GoogleTranslator
from datetime import datetime

# Force real-time log output in GitHub Actions
sys.stdout.reconfigure(line_buffering=True)

# ==========================================
# CONFIGURATION
# ==========================================
DOMAIN = "https://www.egyptphotographytours.com"

TARGET_LANGS = [
    'ar', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'zh-CN', 'ko',
    'hi', 'nl', 'sv', 'pl', 'tr', 'vi', 'th', 'id', 'cs', 'ro',
    'tl', 'no', 'da', 'fi'
]

IGNORE_TAGS = {
    'script', 'style', 'code', 'pre', 'svg', 'math',
    'noscript', 'iframe', 'template', 'textarea', 'input'
}

DELIMITER = " [|||] "
TIMEOUT_SECONDS = 15
MAX_RETRIES = 2
CHUNK_DELAY = 1.5

LANG_META = {
    'en':    {'flag': '🇺🇸', 'name': 'English'},
    'ar':    {'flag': '🇸🇦', 'name': 'العربية'},
    'cs':    {'flag': '🇨🇿', 'name': 'Čeština'},
    'da':    {'flag': '🇩🇰', 'name': 'Dansk'},
    'de':    {'flag': '🇩🇪', 'name': 'Deutsch'},
    'es':    {'flag': '🇪🇸', 'name': 'Español'},
    'fi':    {'flag': '🇫🇮', 'name': 'Suomi'},
    'fr':    {'flag': '🇫🇷', 'name': 'Français'},
    'hi':    {'flag': '🇮🇳', 'name': 'हिन्दी'},
    'id':    {'flag': '🇮🇩', 'name': 'Bahasa Indonesia'},
    'it':    {'flag': '🇮🇹', 'name': 'Italiano'},
    'ja':    {'flag': '🇯🇵', 'name': '日本語'},
    'ko':    {'flag': '🇰🇷', 'name': '한국어'},
    'nl':    {'flag': '🇳🇱', 'name': 'Nederlands'},
    'no':    {'flag': '🇳🇴', 'name': 'Norsk'},
    'pl':    {'flag': '🇵🇱', 'name': 'Polski'},
    'pt':    {'flag': '🇵🇹', 'name': 'Português'},
    'ro':    {'flag': '🇷🇴', 'name': 'Română'},
    'ru':    {'flag': '🇷🇺', 'name': 'Русский'},
    'sv':    {'flag': '🇸🇪', 'name': 'Svenska'},
    'th':    {'flag': '🇹🇭', 'name': 'ไทย'},
    'tl':    {'flag': '🇵🇭', 'name': 'Filipino'},
    'tr':    {'flag': '🇹🇷', 'name': 'Türkçe'},
    'vi':    {'flag': '🇻🇳', 'name': 'Tiếng Việt'},
    'zh-CN': {'flag': '🇨🇳', 'name': '中文 (简体)'}
}

# ==========================================
# URL HELPERS
# ==========================================
def get_relative_url(lang_code, base_path):
    """Generates the correct relative URL for a given language and base path."""
    clean = base_path.replace('index.html', '').replace('.html', '')
    if lang_code == 'en':
        return f"/{clean}" if clean else "/"
    else:
        return f"/{lang_code}/{clean}" if clean else f"/{lang_code}/"

def get_absolute_url(lang_code, base_path):
    """Generates the correct absolute URL for a given language and base path."""
    return f"{DOMAIN}{get_relative_url(lang_code, base_path)}"

# ==========================================
# GIT CHANGE DETECTION (INCREMENTAL)
# ==========================================
def get_changed_english_files():
    """Detects which English files were added or modified in the latest Git push."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'],
            capture_output=True, text=True, check=True
        )
        changed = result.stdout.strip().split('\n')
        return [
            f for f in changed
            if f.endswith('.html')
            and not any(f.startswith(lang + '/') for lang in TARGET_LANGS)
            and os.path.exists(f)
        ]
    except Exception as e:
        print(f"   ⚠️ Git diff failed ({e}). Treating all files as new.", flush=True)
        return []

def get_all_english_files():
    """Finds all English HTML files in the root (excluding language folders)."""
    en_files = []
    for root, dirs, files in os.walk('.'):
        # Skip language folders and hidden/system directories
        dirs[:] = [
            d for d in dirs
            if d not in TARGET_LANGS
            and not d.startswith('.')
            and d not in ['scripts', 'node_modules', '.github']
        ]
        for f in files:
            if f.endswith('.html'):
                en_files.append(os.path.join(root, f))
    return en_files

# ==========================================
# DOM FIREWALL: SAFE TRANSLATION
# ==========================================
def is_translatable(text_node):
    """Checks if a text node is safe to translate (not inside code/script/style)."""
    if isinstance(text_node, Comment):
        return False
    curr = text_node.parent
    while curr:
        if curr.name in IGNORE_TAGS:
            return False
        if curr.get('translate') == 'no':
            return False
        if 'notranslate' in curr.get('class', []):
            return False
        if curr.name == 'head':
            return False  # We handle head tags manually
        curr = curr.parent
    return True

def translate_single_text(translator, text):
    """Translates a single text string with a strict timeout."""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(translator.translate, text)
            return future.result(timeout=TIMEOUT_SECONDS)
    except concurrent.futures.TimeoutError:
        return None
    except Exception:
        return None

def safe_translate(texts, target_lang):
    """
    Translates a list of text strings using chunked batching.
    Includes a 15-second timeout kill-switch to prevent hanging.
    """
    if not texts:
        return []

    translator = GoogleTranslator(source='en', target=target_lang)
    translated_texts = []

    # Step 1: Chunk texts to stay under Google's 5000 character limit
    chunks = []
    current_chunk = []
    current_len = 0

    for t in texts:
        add_len = len(t) + len(DELIMITER)
        if current_len + add_len > 4500 and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_len = 0
        current_chunk.append(t)
        current_len += add_len
    if current_chunk:
        chunks.append(current_chunk)

    # Step 2: Translate each chunk with timeout protection
    for i, chunk in enumerate(chunks):
        payload = DELIMITER.join(chunk)
        res = None

        print(f"      📦 Chunk {i+1}/{len(chunks)} ({len(chunk)} strings) → {target_lang}", flush=True)

        for attempt in range(MAX_RETRIES):
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(translator.translate, payload)
                    res = future.result(timeout=TIMEOUT_SECONDS)
                    break  # Success! Exit retry loop
            except concurrent.futures.TimeoutError:
                print(f"      ⏱️ Timeout on attempt {attempt+1}. Retrying...", flush=True)
                time.sleep(3)
            except Exception as e:
                print(f"      ⚠️ Error: {e}. Retrying...", flush=True)
                time.sleep(3)

        # Step 3: Process the result
        if res:
            parts = res.split(DELIMITER)
            if len(parts) == len(chunk):
                translated_texts.extend(parts)
            else:
                # Delimiter got mangled — fall back to one-by-one
                print(f"      ⚠️ Delimiter mismatch. Falling back to single translation.", flush=True)
                for t in chunk:
                    single_res = translate_single_text(translator, t)
                    translated_texts.append(single_res if single_res else t)
                    time.sleep(0.2)
        else:
            # Google blocked the request entirely — keep English
            print(f"      ❌ Google blocked. Keeping English for this chunk.", flush=True)
            translated_texts.extend(chunk)

        time.sleep(CHUNK_DELAY)  # Rate limit buffer

    return translated_texts

# ==========================================
# EXTRACT & TRANSLATE PAGE CONTENT
# ==========================================
def extract_and_translate(soup, target_lang):
    """Extracts visible text from the DOM, translates it, and injects it back."""
    texts = []
    nodes = []

    # 1. Title tag
    if soup.title and soup.title.string:
        texts.append(soup.title.string.strip())
        nodes.append(('title', soup.title))

    # 2. Meta description and OG tags
    for meta_name in ['description', 'og:title', 'og:description', 'twitter:title', 'twitter:description']:
        tag = soup.find('meta', attrs={'name': meta_name}) or soup.find('meta', attrs={'property': meta_name})
        if tag and tag.get('content'):
            texts.append(tag['content'].strip())
            nodes.append(('meta', tag))

    # 3. Image alt text
    for img in soup.find_all('img', alt=True):
        if img['alt'].strip() and not img['alt'].startswith('http'):
            texts.append(img['alt'].strip())
            nodes.append(('alt', img))

    # 4. Visible text nodes (DOM Firewall applied)
    for text_node in soup.find_all(string=True):
        if is_translatable(text_node):
            original = str(text_node).strip()
            if len(original) > 2 and not original.isspace():
                texts.append(original)
                nodes.append(('text', text_node))

    if not texts:
        return soup

    print(f"      🧠 Translating {len(texts)} strings...", flush=True)
    translated = safe_translate(texts, target_lang)

    if len(translated) == len(nodes):
        for i, (node_type, node) in enumerate(nodes):
            new_text = translated[i]
            if node_type == 'title':
                node.string = new_text
            elif node_type == 'meta':
                node['content'] = new_text
            elif node_type == 'alt':
                node['alt'] = new_text
            elif node_type == 'text':
                node.replace_with(NavigableString(new_text))
    else:
        print(f"      ❌ Array mismatch ({len(translated)} vs {len(nodes)}). Skipping injection.", flush=True)

    return soup

# ==========================================
# FIX INTERNAL LINKS
# ==========================================
def fix_internal_links(soup, target_lang):
    """Prepends the target language prefix to all internal links."""
    for a in soup.find_all('a', href=True):
        href = a['href']

        # Skip external, anchor, and special links
        if href.startswith(('http', 'mailto:', 'tel:', 'javascript:', '#', '//')):
            continue

        # Skip asset files
        if re.search(r'\.(jpg|jpeg|png|gif|svg|webp|css|js|pdf|zip|mp4|webm|ico|woff|woff2|ttf)(\?|$)', href, re.I):
            continue

        # Skip if already has a language prefix
        has_lang_prefix = any(
            href.startswith(f"/{lang}/") or href == f"/{lang}"
            for lang in TARGET_LANGS
        )
        if has_lang_prefix:
            continue

        # Prepend language prefix
        if href.startswith('/'):
            a['href'] = f"/{target_lang}{href}" if href != '/' else f"/{target_lang}/"
        else:
            clean = href.replace('.html', '')
            a['href'] = f"/{target_lang}/{clean}"

    return soup

# ==========================================
# SMART DYNAMIC LANGUAGE MENU BUILDER
# ==========================================
def inject_dynamic_lang_menu(soup, target_lang, base_path):
    """
    Rebuilds the language dropdown menu dynamically.
    Only shows languages whose translated files actually exist on the server.
    This fixes the 'cannot get back to English' bug.
    """
    lang_menu = soup.find('div', id='lang-menu')
    if not lang_menu:
        return soup

    # 1. Remove all old hardcoded language links
    for old_link in lang_menu.find_all('a', class_='lang-item'):
        old_link.decompose()

    # 2. Add English (always present, points to root)
    en_url = get_relative_url('en', base_path)
    en_active = "is-active" if target_lang == 'en' else ""
    en_html = (
        f'<a href="{en_url}" class="lang-item {en_active}" role="menuitem">'
        f'<span class="lang-flag" aria-hidden="true">🇺🇸</span>'
        f'<span class="lang-name">English</span></a>'
    )
    lang_menu.append(BeautifulSoup(en_html, 'lxml'))

    # 3. Add other languages ONLY if the translated file exists
    for lang in TARGET_LANGS:
        translated_path = os.path.join(lang, base_path)
        if os.path.exists(translated_path):
            lang_url = get_relative_url(lang, base_path)
            is_active = "is-active" if target_lang == lang else ""
            flag = LANG_META[lang]['flag']
            name = LANG_META[lang]['name']
            link_html = (
                f'<a href="{lang_url}" class="lang-item {is_active}" role="menuitem">'
                f'<span class="lang-flag" aria-hidden="true">{flag}</span>'
                f'<span class="lang-name">{name}</span></a>'
            )
            lang_menu.append(BeautifulSoup(link_html, 'lxml'))

    return soup

# ==========================================
# GLOBAL SEO INJECTION & SITEMAP GENERATOR
# ==========================================
def inject_global_seo_and_sitemap():
    """
    Scans ALL files on the server, injects perfect canonical + hreflang tags,
    rebuilds language menus, and generates a flawless international sitemap.
    """
    print("\n🔗 Step 3: Injecting SEO Tags & Generating Sitemap...", flush=True)
    page_map = {}

    # 1. Build the page map (group all language versions by base filename)
    for root, dirs, files in os.walk('.'):
        dirs[:] = [
            d for d in dirs
            if not d.startswith('.')
            and d not in ['scripts', 'node_modules', '.github']
        ]
        for f in files:
            if f.endswith('.html'):
                rel = os.path.relpath(os.path.join(root, f), '.')
                base = rel
                lang_code = 'en'
                for lang in TARGET_LANGS:
                    if rel.startswith(f"{lang}/"):
                        base = rel[len(f"{lang}/"):]
                        lang_code = lang
                        break
                if base not in page_map:
                    page_map[base] = {}
                page_map[base][lang_code] = rel

    total_files = sum(len(langs) for langs in page_map.values())
    print(f"   📊 Found {total_files} total pages across {len(page_map)} base files.", flush=True)

    # 2. Inject SEO tags into every file
    processed = 0
    for base, langs in page_map.items():
        for lang_code, rel_path in langs.items():
            if not os.path.exists(rel_path):
                continue

            with open(rel_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'lxml')

            # Remove old canonical and hreflang tags
            for old in soup.find_all('link', rel='alternate'):
                old.decompose()
            for old in soup.find_all('link', rel='canonical'):
                old.decompose()

            head = soup.find('head')
            if not head:
                continue

            # Inject canonical
            canon_url = get_absolute_url(lang_code, base)
            head.append(BeautifulSoup(
                f'<link rel="canonical" href="{canon_url}" />', 'lxml'
            ))

            # Inject hreflang for all existing siblings
            for sib_lang, sib_rel in langs.items():
                sib_url = get_absolute_url(sib_lang, base)
                hl = 'zh' if sib_lang == 'zh-CN' else sib_lang
                head.append(BeautifulSoup(
                    f'<link rel="alternate" hreflang="{hl}" href="{sib_url}" />', 'lxml'
                ))

            # Inject x-default (always points to English)
            en_url = get_absolute_url('en', base)
            head.append(BeautifulSoup(
                f'<link rel="alternate" hreflang="x-default" href="{en_url}" />', 'lxml'
            ))

            # Rebuild language menu
            soup = inject_dynamic_lang_menu(soup, lang_code, base)

            with open(rel_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))

            processed += 1
            if processed % 50 == 0:
                print(f"   ✅ Processed {processed}/{total_files} files...", flush=True)

    print(f"   ✅ SEO tags injected into {processed} files.", flush=True)

    # 3. Generate international sitemap.xml
    today = datetime.now().strftime('%Y-%m-%d')
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">'
    ]

    url_count = 0
    for base, langs in page_map.items():
        for lang_code, rel_path in langs.items():
            if '404.html' in rel_path or 'sitemap.html' in rel_path:
                continue

            url = get_absolute_url(lang_code, base).replace(' ', '%20')

            xml.append('  <url>')
            xml.append(f'    <loc>{url}</loc>')
            xml.append(f'    <lastmod>{today}</lastmod>')

            # Add xhtml:link for every existing language sibling
            for sib_lang, sib_rel in langs.items():
                sib_url = get_absolute_url(sib_lang, base).replace(' ', '%20')
                hl = 'zh' if sib_lang == 'zh-CN' else sib_lang
                xml.append(
                    f'    <xhtml:link rel="alternate" hreflang="{hl}" href="{sib_url}" />'
                )

            # x-default
            en_url = get_absolute_url('en', base).replace(' ', '%20')
            xml.append(
                f'    <xhtml:link rel="alternate" hreflang="x-default" href="{en_url}" />'
            )
            xml.append('  </url>')
            url_count += 1

    xml.append('</urlset>')

    with open('sitemap.xml', 'w', encoding='utf-8') as f:
        f.write('\n'.join(xml))

    print(f"   ✅ sitemap.xml generated with {url_count} URLs.", flush=True)

# ==========================================
# MAIN EXECUTION
# ==========================================
def main():
    print("=" * 60, flush=True)
    print("🚀 Smart Incremental Translation & SEO Pipeline", flush=True)
    print("=" * 60, flush=True)

    # Step 1: Detect changed English files
    print("\n📝 Step 1: Detecting changed English files...", flush=True)
    modified_files = get_changed_english_files()
    all_en_files = get_all_english_files()

    if modified_files:
        print(f"   ✅ Detected {len(modified_files)} changed file(s):", flush=True)
        for f in modified_files:
            print(f"      • {f}", flush=True)
    else:
        print(f"   ℹ️ No changed files detected. Only translating missing pages.", flush=True)

    # Step 2: Translate missing or changed files
    print(f"\n🌍 Step 2: Translating files into {len(TARGET_LANGS)} languages...", flush=True)
    translated_count = 0
    skipped_count = 0

    for en_path in all_en_files:
        rel_path = os.path.relpath(en_path, '.')
        needs_translation = rel_path in modified_files

        with open(en_path, 'r', encoding='utf-8') as f:
            en_soup = BeautifulSoup(f, 'lxml')

        for lang in TARGET_LANGS:
            trans_path = os.path.join(lang, rel_path)

            # ONLY translate if file is missing OR English source was updated
            if not os.path.exists(trans_path) or needs_translation:
                action = "NEW" if not os.path.exists(trans_path) else "UPDATED"
                print(f"   🔄 [{action}] {rel_path} → {lang}", flush=True)

                lang_soup = BeautifulSoup(str(en_soup), 'lxml')
                lang_soup = extract_and_translate(lang_soup, lang)
                lang_soup.html['lang'] = 'zh' if lang == 'zh-CN' else lang
                lang_soup = fix_internal_links(lang_soup, lang)

                os.makedirs(os.path.dirname(trans_path), exist_ok=True)
                with open(trans_path, 'w', encoding='utf-8') as f:
                    f.write(str(lang_soup))

                translated_count += 1
            else:
                skipped_count += 1

    print(f"\n   ✅ Translated: {translated_count} | Skipped (unchanged): {skipped_count}", flush=True)

    # Step 3: Inject SEO tags and generate sitemap
    inject_global_seo_and_sitemap()

    print("\n" + "=" * 60, flush=True)
    print("🎉 Pipeline Complete!", flush=True)
    print("=" * 60, flush=True)

if __name__ == "__main__":
    main()
