#!/usr/bin/env python3
"""
OPUS-MT Smart Translator
- Translates only text nodes (never breaks HTML/Schema)
- Protects URLs, emails, and code from being translated
- Fixes all asset paths and internal links for subfolder usage
- Incremental: only changed files are retranslated
- Batched commits every 5 files (no lost work on cancellation)
- SEO: hreflang, canonical, og:url, lang attributes
"""

import os
import sys
import time
import subprocess
import re
from bs4 import BeautifulSoup
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch

# Force real‑time output so GitHub logs show progress
sys.stdout.reconfigure(line_buffering=True)

# ----------------------------------------------------------------------
# CONFIGURATION – EDIT THESE TO MATCH YOUR SITE
# ----------------------------------------------------------------------
DOMAIN = "https://www.egyptphotographytours.com"   # Your site's full domain (no trailing slash)
SOURCE_LANG = "en"                                 # Your original language (ISO 639‑1)

# All target language folders (must match folder names you want)
TARGET_LANGS = [
    'es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'zh-CN', 'ko', 'ar',
    'hi', 'nl', 'sv', 'pl', 'tr', 'vi', 'th', 'id', 'cs', 'ro',
    'tl', 'no', 'da', 'fi'
]

# Map folder names to OPUS‑MT 2‑letter codes (if different)
OPUS_LANG_MAP = {
    'zh-CN': 'zh',
    'tl': 'tl',
    'no': 'no',
    'da': 'da',
    'fi': 'fi',
}

# ----------------------------------------------------------------------
# URL & EMAIL PROTECTION – Prevents AI from breaking links
# ----------------------------------------------------------------------
def protect_and_restore(text):
    """Replace URLs, emails, and phone numbers with safe placeholders."""
    placeholders = {}
    counter = [0]
    
    def replacer(match):
        key = f"__PROTECTED_{counter[0]}__"
        placeholders[key] = match.group(0)
        counter[0] += 1
        return key
        
    # Protect URLs
    text = re.sub(r'https?://[^\s<>"\']+', replacer, text)
    text = re.sub(r'www\.[^\s<>"\']+', replacer, text)
    # Protect emails
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', replacer, text)
    # Protect phone numbers (e.g., +20 155 073 5673)
    text = re.sub(r'\+\d[\d\s\-\(\)]{8,}\d', replacer, text)
    
    return text, placeholders

def restore_placeholders(text, placeholders):
    for key, val in placeholders.items():
        text = text.replace(key, val)
    return text

def translate_protected_text(text, model, tokenizer):
    """Translate only the non-protected parts of the text."""
    parts = re.split(r'(__PROTECTED_\d+__)', text)
    translated_parts = []
    for part in parts:
        if re.match(r'^__PROTECTED_\d+__$', part):
            translated_parts.append(part) # Keep placeholder as is
        else:
            if part.strip():
                translated_parts.append(translate_text(part, model, tokenizer))
            else:
                translated_parts.append(part)
    return ''.join(translated_parts)

# ----------------------------------------------------------------------
# SMART ASSET PATH FIXING – makes images, CSS, JS work in /es/, /fr/, etc.
# ----------------------------------------------------------------------
def fix_asset_paths(soup):
    """Convert relative asset paths to absolute (starting with '/')."""
    def to_absolute(url):
        if not url or url.startswith(('/','http://','https://','//','data:','#')):
            return url
        if url.startswith('./'):
            url = url[2:]
        elif '../' in url:
            url = re.sub(r'^(\.\./)+', '', url)
        return '/' + url

    for tag in soup.find_all(['img', 'script', 'source', 'iframe', 'video', 'audio', 'track', 'embed']):
        if tag.has_attr('src'):
            tag['src'] = to_absolute(tag['src'])

    for tag in soup.find_all('link', href=True):
        if tag.get('rel') == 'alternate':
            continue
        tag['href'] = to_absolute(tag['href'])

    for tag in soup.find_all('a', href=True):
        href = tag['href']
        if re.search(r'\.(pdf|zip|doc|xls|jpg|png|gif|mp4|webm|ico|svg)(\?|$)', href, re.I):
            tag['href'] = to_absolute(href)

    for tag in soup.find_all(style=True):
        style = tag['style']
        style = re.sub(r'url\([\'"]?\.\.?/([^\'"]+)[\'"]?\)', lambda m: f"url(/{m.group(1)})", style)
        style = re.sub(r'url\([\'"]?([^/\'][^\'"]*)[\'"]?\)', lambda m: f"url(/{m.group(1)})", style)
        tag['style'] = style

    for meta in soup.find_all('meta', attrs={'property': 'og:image'}):
        if meta.has_attr('content'):
            meta['content'] = to_absolute(meta['content'])

    return soup

# ----------------------------------------------------------------------
# INTERNAL LINKS ROUTING – Sends users to the correct language page
# ----------------------------------------------------------------------
def fix_internal_links(soup, target_lang):
    """Prefix internal links with the target language folder."""
    for a in soup.find_all('a', href=True):
        href = a['href']
        
        # Handle absolute URLs that belong to our domain
        if href.startswith(DOMAIN):
            path = href.replace(DOMAIN, '')
            if not path.startswith('/'):
                path = '/' + path
            a['href'] = f"/{target_lang}{path}"
            continue
            
        # Skip external links, anchors, mailto, tel, javascript
        if href.startswith(('http://', 'https://', '//', 'mailto:', 'tel:', 'javascript:', '#')):
            continue
        
        # Skip if already has the target language prefix
        if href.startswith(f"/{target_lang}/") or href == f"/{target_lang}":
            continue
            
        # Skip if it's an asset file
        if re.search(r'\.(jpg|jpeg|png|gif|svg|webp|css|js|pdf|zip|mp4|webm|ico)(\?|$)', href, re.I):
            continue
            
        # If it's an absolute path like /about.html or /blog/
        if href.startswith('/'):
            a['href'] = f"/{target_lang}{href}"
        # If it's a relative path like about.html or blog-page-2.html
        elif href.endswith('.html') or href.endswith('/') or '.' not in href.split('/')[-1]:
            a['href'] = f"/{target_lang}/{href}"
            
    return soup

# ----------------------------------------------------------------------
# SEO: CANONICAL & OG URL FIX
# ----------------------------------------------------------------------
def get_canonical_url(target_lang, rel_path):
    path = rel_path.replace('index.html', '')
    if not path.startswith('/'):
        path = '/' + path
    return f"{DOMAIN}/{target_lang}{path}"

def fix_canonical(soup, target_lang, rel_path):
    canonical = soup.find('link', rel='canonical')
    if canonical:
        canonical['href'] = get_canonical_url(target_lang, rel_path)
    return soup

def fix_og_url(soup, target_lang, rel_path):
    og_url = soup.find('meta', attrs={'property': 'og:url'})
    if og_url:
        og_url['content'] = get_canonical_url(target_lang, rel_path)
    return soup

# ----------------------------------------------------------------------
# GIT HELPERS – commit & push in batches, with rebase to avoid conflicts
# ----------------------------------------------------------------------
def git_commit_and_push(target_lang, file_paths, max_retries=5):
    if not file_paths:
        return
    for attempt in range(max_retries):
        try:
            subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=False)
            subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)
            for f in file_paths:
                subprocess.run(["git", "add", f], check=False)
            subprocess.run(["git", "commit", "-m", f"translate({target_lang}): batch ({len(file_paths)} files)"],
                           check=False, capture_output=True)
            subprocess.run(["git", "pull", "--rebase", "--autostash"], check=False, capture_output=True)
            push_result = subprocess.run(["git", "push"], capture_output=True, text=True)
            if push_result.returncode == 0:
                print(f"    ✅ Committed & pushed {len(file_paths)} files for {target_lang}")
                return
            else:
                print(f"    Push failed (attempt {attempt+1}): {push_result.stderr.strip()}")
                time.sleep(3)
        except Exception as e:
            print(f"    Attempt {attempt+1} error: {e}")
            time.sleep(3)
    print(f"    ⚠️ Push failed after {max_retries} attempts; files are staged locally.")

def get_changed_files():
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'],
            capture_output=True, text=True, check=True
        )
        return [f.strip() for f in result.stdout.split('\n') if f.strip()]
    except Exception:
        return ['FORCE_FULL_RUN']

# ----------------------------------------------------------------------
# OPUS-MT MODEL LOADING & TRANSLATION
# ----------------------------------------------------------------------
def load_model(source_lang, target_lang):
    model_name = f"Helsinki-NLP/opus-mt-{source_lang}-{target_lang}"
    print(f"    Loading {model_name} ...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
    model.eval()
    torch.set_num_threads(2)
    return model, tokenizer

def translate_text(text, model, tokenizer):
    if not text or len(text.strip()) < 3:
        return text
    try:
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            translated_ids = model.generate(**inputs, max_length=512)
        translated = tokenizer.batch_decode(translated_ids, skip_special_tokens=True)[0]
        return translated if translated.strip() else text
    except Exception as e:
        print(f"    Translation error: {e}")
        return text

# ----------------------------------------------------------------------
# HTML TRANSLATION ROUTINES
# ----------------------------------------------------------------------
def translate_metadata_and_attributes(soup, model, tokenizer):
    if soup.title and soup.title.string:
        soup.title.string = translate_text(soup.title.string.strip(), model, tokenizer)
        
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        meta_desc['content'] = translate_text(meta_desc['content'].strip(), model, tokenizer)
        
    for img in soup.find_all('img', alt=True):
        if img['alt'].strip():
            img['alt'] = translate_text(img['alt'].strip(), model, tokenizer)
            
    for inp in soup.find_all('input', placeholder=True):
        if inp['placeholder'].strip():
            inp['placeholder'] = translate_text(inp['placeholder'].strip(), model, tokenizer)
            
    for btn in soup.find_all(['button', 'a'], string=True):
        if btn.string and btn.string.strip():
            btn.string = translate_text(btn.string.strip(), model, tokenizer)
    return soup

def translate_og_twitter(soup, model, tokenizer):
    og_props = ['og:title', 'og:description']
    twitter_names = ['twitter:title', 'twitter:description']
    
    for prop in og_props:
        tag = soup.find('meta', attrs={'property': prop})
        if tag and tag.get('content'):
            tag['content'] = translate_text(tag['content'].strip(), model, tokenizer)
            
    for name in twitter_names:
        tag = soup.find('meta', attrs={'name': name})
        if tag and tag.get('content'):
            tag['content'] = translate_text(tag['content'].strip(), model, tokenizer)
    return soup

def translate_text_nodes(soup, model, tokenizer):
    ignore_tags = {'script', 'style', 'code', 'pre', 'kbd', 'samp', 'var', 'time', 'svg', 'math'}
    
    for text_node in soup.find_all(string=True):
        parent = text_node.parent
        if parent.name in ignore_tags:
            continue
            
        # Skip if parent or any ancestor has translate="no" or class="notranslate"
        skip = False
        current = parent
        while current and current.name:
            if current.get('translate') == 'no' or 'notranslate' in current.get('class', []):
                skip = True
                break
            current = current.parent
        if skip:
            continue
            
        original = str(text_node)
        if not original.strip():
            continue
            
        # Protect URLs/emails, translate text, then restore
        protected_text, placeholders = protect_and_restore(original)
        translated = translate_protected_text(protected_text, model, tokenizer)
        translated = restore_placeholders(translated, placeholders)
        
        if translated and translated != original:
            text_node.replace_with(translated)
            
    return soup

# ----------------------------------------------------------------------
# SEO: ADD HREFLANG ALTERNATES
# ----------------------------------------------------------------------
def add_hreflang_tags(soup, rel_path, target_lang):
    for old in soup.find_all('link', rel='alternate'):
        old.decompose()

    for lang in TARGET_LANGS + ['en']:
        href = get_canonical_url(lang, rel_path)
        tag = soup.new_tag('link', rel='alternate', hreflang=lang, href=href)
        if soup.head:
            soup.head.append(tag)

    default_tag = soup.new_tag('link', rel='alternate', hreflang='x-default',
                               href=get_canonical_url('en', rel_path))
    if soup.head:
        soup.head.append(default_tag)

    # Set the <html lang="..."> attribute correctly
    if soup.html:
        soup.html['lang'] = target_lang if target_lang != 'zh-CN' else 'zh'

    return soup

# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------
def main():
    target = os.getenv('TARGET_LANG')
    if not target or target not in TARGET_LANGS:
        print(f"❌ Invalid target language: {target}")
        return

    opus_lang = OPUS_LANG_MAP.get(target, target)
    print(f"🚀 Translating to {target} (OPUS code: {opus_lang})")

    try:
        model, tokenizer = load_model('en', opus_lang)
        print("✅ Model loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        return

    changed = get_changed_files()
    print(f"📝 Changed files: {changed[:5]}{'...' if len(changed)>5 else ''}")

    out_dir = f"./{target}"
    os.makedirs(out_dir, exist_ok=True)

    ignore_dirs = set(TARGET_LANGS) | {'en', '.git', '.github', '__pycache__', 'node_modules', 'zh', 'ms', 'la'}

    source_files = []
    for f in os.listdir('.'):
        if f.endswith('.html') and os.path.isfile(f):
            source_files.append(f)
    for root, dirs, files in os.walk('.'):
        if root == '.':
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            continue
        for f in files:
            if f.endswith('.html'):
                source_files.append(os.path.join(root, f))

    print(f"🔍 Found {len(source_files)} source HTML files")

    translated = 0
    skipped = 0
    batch = []
    BATCH_SIZE = 5

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

            # 1. Translate metadata, alt texts, placeholders, OG/Twitter
            soup = translate_metadata_and_attributes(soup, model, tokenizer)
            soup = translate_og_twitter(soup, model, tokenizer)
            
            # 2. Translate all visible text nodes (HTML structure unchanged)
            soup = translate_text_nodes(soup, model, tokenizer)
            
            # 3. Fix asset paths (images, CSS, JS) for subfolder use
            soup = fix_asset_paths(soup)
            
            # 4. Fix internal links to point to translated folders
            soup = fix_internal_links(soup, target)
            
            # 5. Fix Canonical and OG URL
            href_path = rel.replace('index.html', '')
            soup = fix_canonical(soup, target, href_path)
            soup = fix_og_url(soup, target, href_path)
            
            # 6. Add SEO hreflang tags and set html lang
            soup = add_hreflang_tags(soup, href_path, target)

            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))

            translated += 1
            batch.append(out_path)

            if len(batch) >= BATCH_SIZE:
                git_commit_and_push(target, batch)
                batch = []
        except Exception as e:
            print(f"  ❌ Error processing {rel}: {e}")

    if batch:
        git_commit_and_push(target, batch)

    print(f"✅ Done: translated {translated}, skipped {skipped} for {target}")

if __name__ == "__main__":
    main()
