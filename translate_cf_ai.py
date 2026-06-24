#!/usr/bin/env python3
"""
Cloudflare Workers AI Premium Translator
- Uses Cloudflare's Meta M2M-100 model for fast, high-quality translation
- 100% safe for HTML (extracts text, translates, and re-injects)
- Bulletproof link & asset routing
- Deploys to GitHub every 20 pages
- Gracefully handles Cloudflare's daily Neuron limits
"""

import os
import sys
import time
import subprocess
import re
import json
import requests
from bs4 import BeautifulSoup, Comment

sys.stdout.reconfigure(line_buffering=True)

# ----------------------------------------------------------------------
# CONFIGURATION
# ----------------------------------------------------------------------
DOMAIN = "https://www.egyptphotographytours.com"
SOURCE_LANG = "en"

TARGET_LANGS = [
    'ar', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'zh-CN', 'ko',
    'hi', 'nl', 'sv', 'pl', 'tr', 'vi', 'th', 'id', 'cs', 'ro',
    'tl', 'no', 'da', 'fi'
]

# Cloudflare M2M-100 uses 3-letter ISO codes
CF_LANG_MAP = {
    'ar': 'ara', 'es': 'spa', 'fr': 'fra', 'de': 'deu', 'it': 'ita', 
    'pt': 'por', 'ru': 'rus', 'ja': 'jpn', 'zh-CN': 'zho', 'ko': 'kor', 
    'hi': 'hin', 'nl': 'nld', 'sv': 'swe', 'pl': 'pol', 'tr': 'tur', 
    'vi': 'vie', 'th': 'tha', 'id': 'ind', 'cs': 'ces', 'ro': 'ron', 
    'tl': 'tgl', 'no': 'nob', 'da': 'dan', 'fi': 'fin'
}

# Cloudflare API Setup
CF_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
CF_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN")
CF_AI_URL = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/meta/m2m100-1.2b"
CF_HEADERS = {"Authorization": f"Bearer {CF_API_TOKEN}"}

# ----------------------------------------------------------------------
# CLOUDFLARE AI TRANSLATION ENGINE
# ----------------------------------------------------------------------
def translate_with_cf(text, target_lang_code):
    """Sends text to Cloudflare Workers AI."""
    target_lang = CF_LANG_MAP.get(target_lang_code)
    if not target_lang or not text.strip():
        return text

    payload = {
        "text": text,
        "source_lang": "eng",
        "target_lang": target_lang
    }
    
    for attempt in range(3):
        try:
            response = requests.post(CF_AI_URL, headers=CF_HEADERS, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                return result.get("result", {}).get("translated_text", text)
            
            elif response.status_code == 429 or "quota" in response.text.lower():
                print(f"    🛑 Cloudflare Neuron limit reached for today. Stopping safely.")
                return "CF_LIMIT_REACHED" # Signal to stop the whole page processing
                
            else:
                print(f"    ⚠️ CF API Error {response.status_code}: {response.text[:100]}")
                time.sleep(5)
                
        except Exception as e:
            print(f"    ⚠️ Network Error: {e}")
            time.sleep(5)
            
    return text

# ----------------------------------------------------------------------
# HTML PARSING & EXTRACTION
# ----------------------------------------------------------------------
def extract_and_translate_page(soup, target_lang):
    """Extracts all translatable text, sends to CF AI, and re-injects."""
    elements_to_translate = []
    
    # 1. Meta Tags
    if soup.title and soup.title.string: elements_to_translate.append(('title', soup.title, soup.title.string.strip()))
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'): elements_to_translate.append(('meta', meta_desc, meta_desc['content'].strip()))
    
    for prop in ['og:title', 'og:description', 'twitter:title', 'twitter:description']:
        tag = soup.find('meta', attrs={'property': prop}) or soup.find('meta', attrs={'name': prop})
        if tag and tag.get('content'): elements_to_translate.append(('meta', tag, tag['content'].strip()))

    # 2. Image Alts
    for img in soup.find_all('img', alt=True):
        if img['alt'].strip() and not img['alt'].startswith('http'):
            elements_to_translate.append(('alt', img, img['alt'].strip()))

    # 3. Body Text Nodes (Paragraphs, Headings, List Items, Links)
    target_tags = {'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'span', 'a', 'td', 'th', 'label', 'button'}
    for tag in soup.find_all(target_tags):
        # Get direct text, ignoring nested HTML tags
        direct_text = tag.find(string=True, recursive=False)
        if direct_text and isinstance(direct_text, str) and len(direct_text.strip()) > 2:
            # Skip if it's inside a script/style or head
            if tag.find_parent(['script', 'style', 'head']): continue
            elements_to_translate.append(('text', tag, direct_text.strip()))

    print(f"    🧠 Sending {len(elements_to_translate)} strings to Cloudflare AI...")
    
    limit_reached = False
    for i, (elem_type, elem, original_text) in enumerate(elements_to_translate):
        if limit_reached: break
        
        translated = translate_with_cf(original_text, target_lang)
        
        if translated == "CF_LIMIT_REACHED":
            limit_reached = True
            break
            
        # Re-inject safely
        if elem_type == 'title': elem.string = translated
        elif elem_type == 'meta': elem['content'] = translated
        elif elem_type == 'alt': elem['alt'] = translated
        elif elem_type == 'text': 
            # Replace the specific text node inside the tag
            for child in elem.children:
                if isinstance(child, str) and child.strip() == original_text:
                    child.replace_with(translated)
                    break
                    
    if limit_reached:
        print(f"    ⏸️ Pausing translation for {target_lang} due to daily API limits. Progress saved.")
        
    return soup, limit_reached

# ----------------------------------------------------------------------
# SMART ASSET & LINK ROUTING (BULLETPROOF)
# ----------------------------------------------------------------------
def fix_asset_paths(soup):
    def to_absolute(url):
        if not url or url.startswith(('/','http://','https://','//','data:','#')): return url
        if url.startswith('./'): url = url[2:]
        elif '../' in url: url = re.sub(r'^(\.\./)+', '', url)
        return '/' + url
    for tag in soup.find_all(['img', 'script', 'source', 'iframe', 'video', 'audio', 'track', 'embed']):
        if tag.has_attr('src'): tag['src'] = to_absolute(tag['src'])
    for tag in soup.find_all('link', href=True):
        if tag.get('rel') == 'alternate': continue
        tag['href'] = to_absolute(tag['href'])
    for tag in soup.find_all(style=True):
        style = tag['style']
        style = re.sub(r'url\([\'"]?\.\.?/([^\'"]+)[\'"]?\)', lambda m: f"url(/{m.group(1)})", style)
        tag['style'] = style
    return soup

def fix_internal_links(soup, target_lang):
    all_langs = TARGET_LANGS + ['en']
    def clean_relative_path(href):
        while href.startswith('./'): href = href[2:]
        while href.startswith('../'): href = href[3:]
        return href
    def has_lang_prefix(href):
        return any(href.startswith(f"/{lang}/") or href == f"/{lang}" for lang in all_langs)

    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith(DOMAIN):
            path = clean_relative_path(href.replace(DOMAIN, ''))
            if not path.startswith('/'): path = '/' + path
            a['href'] = path if has_lang_prefix(path) else f"/{target_lang}{path}"
            continue
        if href.startswith(('http://', 'https://', '//', 'mailto:', 'tel:', 'javascript:', '#')): continue
        if re.search(r'\.(jpg|jpeg|png|gif|svg|webp|css|js|pdf|zip|mp4|webm|ico)(\?|$)', href, re.I): continue
        href = clean_relative_path(href)
        if not href.startswith('/'): href = '/' + href
        if has_lang_prefix(href): a['href'] = href
        else: a['href'] = f"/{target_lang}{href}"
    return soup

# ----------------------------------------------------------------------
# SEO & GIT HELPERS
# ----------------------------------------------------------------------
def get_canonical_url(target_lang, rel_path):
    path = rel_path.replace('index.html', '')
    if not path.startswith('/'): path = '/' + path
    return f"{DOMAIN}/{target_lang}{path}"

def fix_seo_tags(soup, target_lang, rel_path):
    canonical = soup.find('link', rel='canonical')
    if canonical: canonical['href'] = get_canonical_url(target_lang, rel_path)
    og_url = soup.find('meta', attrs={'property': 'og:url'})
    if og_url: og_url['content'] = get_canonical_url(target_lang, rel_path)
    
    for old in soup.find_all('link', rel='alternate'): old.decompose()
    for lang in TARGET_LANGS + ['en']:
        href = get_canonical_url(lang, rel_path)
        tag = soup.new_tag('link', rel='alternate', hreflang=lang, href=href)
        if soup.head: soup.head.append(tag)
    default_tag = soup.new_tag('link', rel='alternate', hreflang='x-default', href=get_canonical_url('en', rel_path))
    if soup.head: soup.head.append(default_tag)
    if soup.html: soup.html['lang'] = target_lang if target_lang != 'zh-CN' else 'zh'
    return soup

def git_commit_and_push(target_lang, file_paths, max_retries=3):
    if not file_paths: return
    for attempt in range(max_retries):
        try:
            subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=False)
            subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)
            for f in file_paths: subprocess.run(["git", "add", f], check=False)
            subprocess.run(["git", "commit", "-m", f"translate-cf({target_lang}): batch ({len(file_paths)} files)"], check=False, capture_output=True)
            subprocess.run(["git", "pull", "--rebase", "--autostash"], check=False, capture_output=True)
            branch_name = os.getenv('GITHUB_REF_NAME', 'main')
            push_result = subprocess.run(["git", "push", "origin", f"HEAD:{branch_name}"], capture_output=True, text=True)
            if push_result.returncode == 0:
                print(f"    ✅ Committed & pushed {len(file_paths)} files for {target_lang}")
                return True
            else: time.sleep(3)
        except Exception as e: time.sleep(3)
    return False

def get_changed_files():
    try:
        result = subprocess.run(['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'], capture_output=True, text=True, check=True)
        return [f.strip() for f in result.stdout.split('\n') if f.strip()]
    except Exception: return ['FORCE_FULL_RUN']

# ----------------------------------------------------------------------
# MAIN EXECUTION
# ----------------------------------------------------------------------
def main():
    target = os.getenv('TARGET_LANG')
    if not target or target not in TARGET_LANGS:
        print(f"❌ Invalid target language: {target}")
        return

    print(f"🚀 Translating to {target} using Cloudflare Workers AI")

    changed = get_changed_files()
    out_dir = f"./{target}"
    os.makedirs(out_dir, exist_ok=True)
    ignore_dirs = set(TARGET_LANGS) | {'en', '.git', '.github', '__pycache__', 'node_modules', 'zh', 'ms', 'la'}

    source_files = []
    for f in os.listdir('.'):
        if f.endswith('.html') and os.path.isfile(f): source_files.append(f)
    for root, dirs, files in os.walk('.'):
        if root == '.':
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            continue
        for f in files:
            if f.endswith('.html'): source_files.append(os.path.join(root, f))

    translated = 0
    skipped = 0
    batch = []
    BATCH_SIZE = 20

    for src in source_files:
        rel = src[2:] if src.startswith('./') else src
        out_path = os.path.join(out_dir, rel)
        
        if os.path.exists(out_path) and rel not in changed and 'FORCE_FULL_RUN' not in changed:
            skipped += 1
            continue

        print(f"  🔄 {rel}")
        try:
            with open(src, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f.read(), 'html.parser')

            # 1. AI Translation
            soup, limit_hit = extract_and_translate_page(soup, target)
            
            # 2. Fix Routing & SEO
            soup = fix_asset_paths(soup)
            soup = fix_internal_links(soup, target)
            href_path = rel.replace('index.html', '')
            soup = fix_seo_tags(soup, target, href_path)

            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))

            translated += 1
            batch.append(out_path)
            
            if len(batch) >= BATCH_SIZE:
                git_commit_and_push(target, batch)
                batch = []
                
            # If Cloudflare limit was hit, stop processing further files for this language today
            if limit_hit:
                if batch: git_commit_and_push(target, batch)
                print(f"🛑 Daily Cloudflare Neuron limit reached. Stopping {target} safely. Run again tomorrow to continue.")
                return 
                
        except Exception as e:
            print(f"  ❌ Error processing {rel}: {e}")

    if batch: git_commit_and_push(target, batch)
    print(f"✅ Done: translated {translated}, skipped {skipped} for {target}")

if __name__ == "__main__":
    main()
