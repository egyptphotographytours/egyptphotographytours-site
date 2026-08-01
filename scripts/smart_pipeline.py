#!/usr/bin/env python3
"""
Ultimate Smart Incremental Translation & SEO Pipeline
=====================================================
- Translates ONLY new or changed English files (incremental)
- DOM Firewall: Protects DOCTYPE, <script>, <style>, JSON-LD from translation
- Smart Dynamic Menu: Rebuilds language dropdown to prevent 404s
- 15-second timeout kill-switch to prevent Google Translate from hanging
- BATCH PUSH: Commits and pushes every 30 files to prevent timeout data loss
- GSC Indexing: Injects perfect canonical + hreflang tags based on actual files
- Generates flawless international sitemap.xml with xhtml:link tags
"""

import os
import re
import sys
import time
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
BATCH_SIZE = 30 # ✅ Push to GitHub after every 30 translated files

TARGET_LANGS = [
    'ar', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'zh-CN', 'ko',
    'hi', 'nl', 'sv', 'pl', 'tr', 'vi', 'th', 'id', 'cs', 'ro',
    'tl', 'no', 'da', 'fi'
]

IGNORE_TAGS = {
    'script', 'style', 'code', 'pre', 'svg', 'math',
    'noscript', 'iframe', 'template', 'textarea', 'input'
}

DELIMITER = "\n" # Newline is perfectly preserved by Google Translate (even in RTL Arabic)
TIMEOUT_SECONDS = 15
MAX_RETRIES = 2
CHUNK_DELAY = 1.5

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
    else:
        return f"/{lang_code}/{clean}" if clean else f"/{lang_code}/"

def get_absolute_url(lang_code, base_path):
    rel_url = get_relative_url(lang_code, base_path)
    return f"{DOMAIN}{rel_url}"

# ==========================================
# GIT CHANGE DETECTION (INCREMENTAL)
# ==========================================
def get_changed_english_files():
    try:
        result = subprocess.run(['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'], capture_output=True, text=True, check=True)
        changed = result.stdout.strip().split('\n')
        return [f for f in changed if f.endswith('.html') and not any(f.startswith(lang + '/') for lang in TARGET_LANGS) and os.path.exists(f)]
    except Exception:
        return []

def get_all_english_files():
    en_files = []
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in TARGET_LANGS and not d.startswith('.') and d not in ['scripts', 'node_modules', '.github']]
        for f in files:
            if f.endswith('.html'):
                en_files.append(os.path.join(root, f))
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

def translate_single_text(translator, text):
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(translator.translate, text)
            return future.result(timeout=TIMEOUT_SECONDS)
    except:
        return None

def safe_translate(texts, target_lang):
    if not texts: return []
    translator = GoogleTranslator(source='en', target=target_lang)
    translated_texts = []
    chunks, current_chunk, current_len = [], [], 0

    for t in texts:
        clean_t = t.replace('\n', ' ').replace('\r', ' ').strip()
        if not clean_t: clean_t = t 
        add_len = len(clean_t) + 1
        if current_len + add_len > 4500 and current_chunk:
            chunks.append(current_chunk)
            current_chunk, current_len = [], 0
        current_chunk.append(clean_t)
        current_len += add_len
    if current_chunk: chunks.append(current_chunk)

    for i, chunk in enumerate(chunks):
        payload = "\n".join(chunk)
        res = None
        print(f"      📦 Chunk {i+1}/{len(chunks)} ({len(chunk)} strings) → {target_lang}", flush=True)

        for attempt in range(MAX_RETRIES):
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(translator.translate, payload)
                    res = future.result(timeout=TIMEOUT_SECONDS)
                    break
            except concurrent.futures.TimeoutError:
                print(f"      ⏱️ Timeout on attempt {attempt+1}. Retrying...", flush=True)
                time.sleep(3)
            except Exception as e:
                print(f"      ⚠️ Error: {e}. Retrying...", flush=True)
                time.sleep(3)

        if res:
            parts = res.split("\n")
            if len(parts) == len(chunk):
                translated_texts.extend(parts)
            else:
                print(f"      ⚠️ Newline mismatch. Falling back to single translation.", flush=True)
                for t in chunk:
                    single_res = translate_single_text(translator, t)
                    translated_texts.append(single_res if single_res else t)
                    time.sleep(0.2)
        else:
            print(f"      ❌ Google blocked. Keeping English for this chunk.", flush=True)
            translated_texts.extend(chunk)
        time.sleep(CHUNK_DELAY)
    return translated_texts

def extract_and_translate(soup, target_lang):
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
                
    if not texts: return soup

    print(f"      🧠 Translating {len(texts)} strings...", flush=True)
    translated = safe_translate(texts, target_lang)
    if len(translated) == len(nodes):
        for i, (node_type, node) in enumerate(nodes):
            new_text = translated[i]
            if node_type == 'title': node.string = new_text
            elif node_type == 'meta': node['content'] = new_text
            elif node_type == 'alt': node['alt'] = new_text
            elif node_type == 'text': node.replace_with(NavigableString(new_text))
    return soup

def fix_internal_links(soup, target_lang):
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith(('http', 'mailto:', 'tel:', 'javascript:', '#', '//')): continue
        if re.search(r'\.(jpg|jpeg|png|gif|svg|webp|css|js|pdf|zip|mp4|webm|ico|woff|woff2|ttf)(\?|$)', href, re.I): continue
        if any(href.startswith(f"/{lang}/") or href == f"/{lang}" for lang in TARGET_LANGS): continue
        if href.startswith('/'):
            a['href'] = f"/{target_lang}{href}" if href != '/' else f"/{target_lang}/"
        else:
            clean_href = href.replace('.html', '')
            a['href'] = f"/{target_lang}/{clean_href}"
    return soup

def inject_dynamic_lang_menu(soup, target_lang, base_path):
    lang_menu = soup.find('div', id='lang-menu')
    if not lang_menu: return soup
    for old_link in lang_menu.find_all('a', class_='lang-item'): old_link.decompose()
    
    en_url = get_relative_url('en', base_path)
    en_active = "is-active" if target_lang == 'en' else ""
    en_html = f'<a href="{en_url}" class="lang-item {en_active}" role="menuitem"><span class="lang-flag" aria-hidden="true">🇺🇸</span><span class="lang-name">English</span></a>'
    lang_menu.append(BeautifulSoup(en_html, 'lxml'))
    
    for lang in TARGET_LANGS:
        if os.path.exists(os.path.join(lang, base_path)):
            lang_url = get_relative_url(lang, base_path)
            is_active = "is-active" if target_lang == lang else ""
            flag = LANG_META[lang]['flag']
            name = LANG_META[lang]['name']
            link_html = f'<a href="{lang_url}" class="lang-item {is_active}" role="menuitem"><span class="lang-flag" aria-hidden="true">{flag}</span><span class="lang-name">{name}</span></a>'
            lang_menu.append(BeautifulSoup(link_html, 'lxml'))
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
                if base not in page_map: page_map[base] = {}
                page_map[base][lang_code] = rel

    for base, langs in page_map.items():
        for lang_code, rel_path in langs.items():
            if not os.path.exists(rel_path): continue
            with open(rel_path, 'r', encoding='utf-8') as f: 
                soup = BeautifulSoup(f, 'lxml')
                
            for old in soup.find_all('link', rel='alternate'): old.decompose()
            for old in soup.find_all('link', rel='canonical'): old.decompose()
            head = soup.find('head')
            if not head: continue
            
            canon_url = get_absolute_url(lang_code, base)
            head.append(BeautifulSoup(f'<link rel="canonical" href="{canon_url}" />', 'lxml'))
            
            for sib_lang, sib_rel in langs.items():
                hl = 'zh' if sib_lang == 'zh-CN' else sib_lang
                sib_url = get_absolute_url(sib_lang, base)
                head.append(BeautifulSoup(f'<link rel="alternate" hreflang="{hl}" href="{sib_url}" />', 'lxml'))
                
            en_url = get_absolute_url('en', base)
            head.append(BeautifulSoup(f'<link rel="alternate" hreflang="x-default" href="{en_url}" />', 'lxml'))
            
            soup = inject_dynamic_lang_menu(soup, lang_code, base)
            with open(rel_path, 'w', encoding='utf-8') as f: 
                f.write(str(soup))

    today = datetime.now().strftime('%Y-%m-%d')
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    
    for base, langs in page_map.items():
        for lang_code, rel_path in langs.items():
            if '404.html' in rel_path or 'sitemap.html' in rel_path: continue
            
            url = get_absolute_url(lang_code, base).replace(' ', '%20')
            xml.append(f'  <url>\n    <loc>{url}</loc>\n    <lastmod>{today}</lastmod>')
            
            for sib_lang, sib_rel in langs.items():
                hl = 'zh' if sib_lang == 'zh-CN' else sib_lang
                sib_url = get_absolute_url(sib_lang, base).replace(' ', '%20')
                xml.append(f'    <xhtml:link rel="alternate" hreflang="{hl}" href="{sib_url}" />')
                
            en_url = get_absolute_url('en', base).replace(' ', '%20')
            xml.append(f'    <xhtml:link rel="alternate" hreflang="x-default" href="{en_url}" />\n  </url>')
            
    xml.append('</urlset>')
    with open('sitemap.xml', 'w', encoding='utf-8') as f: 
        f.write('\n'.join(xml))
    print("   ✅ sitemap.xml generated.", flush=True)

# ==========================================
# MAIN EXECUTION
# ==========================================
def main():
    print("=" * 60, flush=True)
    print("🚀 Smart Incremental Translation & SEO Pipeline", flush=True)
    print("=" * 60, flush=True)

    modified_files = get_changed_english_files()
    all_en_files = get_all_english_files()
    
    files_generated_since_push = 0

    print(f"\n🌍 Step 2: Translating files into {len(TARGET_LANGS)} languages...", flush=True)
    for en_path in all_en_files:
        rel_path = os.path.relpath(en_path, '.')
        needs_translation = rel_path in modified_files

        with open(en_path, 'r', encoding='utf-8') as f: 
            en_soup = BeautifulSoup(f, 'lxml')

        for lang in TARGET_LANGS:
            trans_path = os.path.join(lang, rel_path)
            if not os.path.exists(trans_path) or needs_translation:
                
                action = 'NEW' if not os.path.exists(trans_path) else 'UPDATED'
                print(f"   🔄 [{action}] {rel_path} → {lang}", flush=True)
                
                lang_soup = BeautifulSoup(str(en_soup), 'lxml')
                lang_soup = extract_and_translate(lang_soup, lang)
                lang_soup.html['lang'] = 'zh' if lang == 'zh-CN' else lang
                lang_soup = fix_internal_links(lang_soup, lang)
                
                os.makedirs(os.path.dirname(trans_path), exist_ok=True)
                with open(trans_path, 'w', encoding='utf-8') as f: 
                    f.write(str(lang_soup))
                
                files_generated_since_push += 1
                
                # ✅ PUSH EVERY 30 FILES
                if files_generated_since_push >= BATCH_SIZE:
                    batch_commit_and_push(files_generated_since_push)
                    files_generated_since_push = 0

    if files_generated_since_push > 0:
        batch_commit_and_push(files_generated_since_push)

    inject_global_seo_and_sitemap()
    print("\n🎉 Pipeline Complete!", flush=True)

if __name__ == "__main__":
    main()
