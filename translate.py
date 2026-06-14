#!/usr/bin/env python3
"""
OPUS-MT Smart Translator
- Translates only text nodes (never breaks HTML)
- Fixes all asset paths (images, CSS, JS) for subfolder usage
- Incremental: only changed files are retranslated
- Batched commits every 5 files (no lost work on cancellation)
- SEO: hreflang + lang attributes
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
# SMART ASSET PATH FIXING – makes images, CSS, JS work in /es/, /fr/, etc.
# ----------------------------------------------------------------------
def fix_asset_paths(soup):
    """Convert relative asset paths to absolute (starting with '/')."""
    def to_absolute(url):
        if not url or url.startswith(('/','http://','https://','//','data:','#')):
            return url
        # Remove leading './' or '../' chains
        if url.startswith('./'):
            url = url[2:]
        elif '../' in url:
            # Collapse all '../' and then make absolute
            url = re.sub(r'^(\.\./)+', '', url)
        # Now it's e.g., "images/logo.png" -> "/images/logo.png"
        return '/' + url

    # Rewrite src attributes (images, scripts, iframes, etc.)
    for tag in soup.find_all(['img', 'script', 'source', 'iframe', 'video', 'audio', 'track', 'embed']):
        if tag.has_attr('src'):
            tag['src'] = to_absolute(tag['src'])

    # Rewrite href attributes for external resources (CSS, favicon, preconnect)
    # But skip alternate/hreflang links – they are added later by the script.
    for tag in soup.find_all('link', href=True):
        if tag.get('rel') == 'alternate':
            continue
        tag['href'] = to_absolute(tag['href'])

    # For <a> tags that point to downloadable files (PDF, images, etc.)
    for tag in soup.find_all('a', href=True):
        href = tag['href']
        if re.search(r'\.(pdf|zip|doc|xls|jpg|png|gif|mp4|webm|ico|svg)(\?|$)', href, re.I):
            tag['href'] = to_absolute(href)
        # Leave other <a> hrefs unchanged (internal page links like "about.html")

    # Inline styles with background images
    for tag in soup.find_all(style=True):
        style = tag['style']
        # Fix url(relative) and url(../relative)
        style = re.sub(r'url\([\'"]?\.\.?/([^\'"]+)[\'"]?\)', lambda m: f"url(/{m.group(1)})", style)
        style = re.sub(r'url\([\'"]?([^/\'][^\'"]*)[\'"]?\)', lambda m: f"url(/{m.group(1)})", style)
        tag['style'] = style

    # Open Graph image
    for meta in soup.find_all('meta', attrs={'property': 'og:image'}):
        if meta.has_attr('content'):
            meta['content'] = to_absolute(meta['content'])

    return soup


# ----------------------------------------------------------------------
# GIT HELPERS – commit & push in batches, with rebase to avoid conflicts
# ----------------------------------------------------------------------
def git_commit_and_push(target_lang, file_paths, max_retries=5):
    """Add, commit, and push a batch of files. Retries with pull --rebase."""
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
    """Return list of files changed in the last commit (relative paths)."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'],
            capture_output=True, text=True, check=True
        )
        return [f.strip() for f in result.stdout.split('\n') if f.strip()]
    except Exception:
        # If git diff fails (e.g., first commit), translate everything
        return ['FORCE_FULL_RUN']


# ----------------------------------------------------------------------
# OPUS-MT MODEL LOADING & TRANSLATION
# ----------------------------------------------------------------------
def load_model(source_lang, target_lang):
    """Load the OPUS-MT model for a specific language pair."""
    model_name = f"Helsinki-NLP/opus-mt-{source_lang}-{target_lang}"
    print(f"    Loading {model_name} ...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
    model.eval()
    torch.set_num_threads(2)   # Prevent CPU overload on GitHub runner
    return model, tokenizer


def translate_text(text, model, tokenizer):
    """Translate a single string using the loaded model."""
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
# HTML TRANSLATION ROUTINES – preserve structure, only change text
# ----------------------------------------------------------------------
def translate_metadata_and_attributes(soup, model, tokenizer):
    """Translate <title>, meta description, alt texts, placeholders, button texts."""
    # Title
    if soup.title and soup.title.string:
        soup.title.string = translate_text(soup.title.string.strip(), model, tokenizer)
    # Meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        meta_desc['content'] = translate_text(meta_desc['content'].strip(), model, tokenizer)
    # Image alt text
    for img in soup.find_all('img', alt=True):
        if img['alt'].strip():
            img['alt'] = translate_text(img['alt'].strip(), model, tokenizer)
    # Input placeholders
    for inp in soup.find_all('input', placeholder=True):
        if inp['placeholder'].strip():
            inp['placeholder'] = translate_text(inp['placeholder'].strip(), model, tokenizer)
    # Button and link text (if they are direct text nodes)
    for btn in soup.find_all(['button', 'a'], string=True):
        if btn.string and btn.string.strip():
            btn.string = translate_text(btn.string.strip(), model, tokenizer)
    return soup


def translate_text_nodes(soup, model, tokenizer):
    """
    Translate every visible text node while leaving all HTML tags untouched.
    Ignores script, style, code, etc.
    """
    ignore_tags = {'script', 'style', 'code', 'pre', 'kbd', 'samp', 'var', 'time'}
    for text_node in soup.find_all(string=True):
        parent = text_node.parent
        if parent.name in ignore_tags:
            continue
        if not text_node.strip():
            continue
        original = text_node.strip()
        translated = translate_text(original, model, tokenizer)
        if translated and translated != original:
            text_node.replace_with(translated)
    return soup


# ----------------------------------------------------------------------
# SEO: ADD HREFLANG ALTERNATES
# ----------------------------------------------------------------------
def add_hreflang_tags(soup, rel_path):
    """
    Insert <link rel="alternate" hreflang="xx" href="..."> for all languages,
    plus an x-default version.
    """
    # Remove any existing alternates (to avoid duplication)
    for old in soup.find_all('link', rel='alternate'):
        old.decompose()

    for lang in TARGET_LANGS + ['en']:
        href = f"{DOMAIN}/{lang}/{rel_path}"
        tag = soup.new_tag('link', rel='alternate', hreflang=lang, href=href)
        if soup.head:
            soup.head.append(tag)

    # x-default points to English version (or root)
    default_tag = soup.new_tag('link', rel='alternate', hreflang='x-default',
                               href=f"{DOMAIN}/{rel_path}")
    if soup.head:
        soup.head.append(default_tag)

    # Also set the <html lang="..."> attribute
    if soup.html:
        soup.html['lang'] = lang if lang != 'zh-CN' else 'zh'

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

    # Load model (cached by GitHub Actions, so subsequent runs are fast)
    try:
        model, tokenizer = load_model('en', opus_lang)
        print("✅ Model loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        return

    # Which files changed in the last commit?
    changed = get_changed_files()
    print(f"📝 Changed files: {changed[:5]}{'...' if len(changed)>5 else ''}")

    out_dir = f"./{target}"
    os.makedirs(out_dir, exist_ok=True)

    # Folders to ignore while scanning for source HTML files
    ignore_dirs = set(TARGET_LANGS) | {'en', '.git', '.github', '__pycache__', 'node_modules', 'zh', 'ms', 'la'}

    source_files = []
    # HTML files directly in repository root
    for f in os.listdir('.'):
        if f.endswith('.html') and os.path.isfile(f):
            source_files.append(f)
    # HTML files in subdirectories (skip ignored folders)
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
    BATCH_SIZE = 5          # Commit every 5 files (adjust as you like)

    for src in source_files:
        rel = src[2:] if src.startswith('./') else src
        out_path = os.path.join(out_dir, rel)

        # Incremental skip: if already translated and source unchanged
        if os.path.exists(out_path) and rel not in changed and 'FORCE_FULL_RUN' not in changed:
            skipped += 1
            continue

        print(f"  🔄 {rel}")
        try:
            with open(src, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f.read(), 'html.parser')

            # 1. Translate metadata, alt texts, placeholders
            soup = translate_metadata_and_attributes(soup, model, tokenizer)
            # 2. Translate all visible text nodes (HTML structure unchanged)
            soup = translate_text_nodes(soup, model, tokenizer)
            # 3. Fix asset paths (images, CSS, JS) for subfolder use
            soup = fix_asset_paths(soup)
            # 4. Add SEO hreflang tags
            href_path = rel.replace('index.html', '')
            soup = add_hreflang_tags(soup, href_path)

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

    # Push any remaining files
    if batch:
        git_commit_and_push(target, batch)

    print(f"✅ Done: translated {translated}, skipped {skipped} for {target}")


if __name__ == "__main__":
    main()
