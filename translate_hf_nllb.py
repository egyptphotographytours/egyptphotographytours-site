#!/usr/bin/env python3
"""
Hugging Face NLLB-200 Premium Translator (cURL Edition)
- Uses native 'curl' to completely bypass Python's DNS resolution bugs
- Uses Meta's state-of-the-art NLLB-200 model (200 languages)
- 100% safe for HTML (extracts text, translates, and re-injects)
- Bulletproof link & asset routing
- Deploys to GitHub every 20 pages
"""

import os
import sys
import time
import subprocess
import re
import json
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

NLLB_LANG_MAP = {
    'ar': 'arb_Arab', 'es': 'spa_Latn', 'fr': 'fra_Latn', 'de': 'deu_Latn', 
    'it': 'ita_Latn', 'pt': 'por_Latn', 'ru': 'rus_Cyrl', 'ja': 'jpn_Jpan', 
    'zh-CN': 'zho_Hans', 'ko': 'kor_Hang', 'hi': 'hin_Deva', 'nl': 'nld_Latn', 
    'sv': 'swe_Latn', 'pl': 'pol_Latn', 'tr': 'tur_Latn', 'vi': 'vie_Latn', 
    'th': 'tha_Thai', 'id': 'ind_Latn', 'cs': 'ces_Latn', 'ro': 'ron_Latn', 
    'tl': 'tgl_Latn', 'no': 'nob_Latn', 'da': 'dan_Latn', 'fi': 'fin_Latn'
}

HF_TOKEN = os.environ.get("HF_TOKEN")
API_URL = "https://api-inference.huggingface.co/models/facebook/nllb-200-distilled-600M"

# ----------------------------------------------------------------------
# HUGGING FACE NLLB TRANSLATION ENGINE (USING NATIVE CURL)
# ----------------------------------------------------------------------
def translate_batch_with_nllb(texts, target_lang_code):
    """Sends a batch of text to HF NLLB-200 using native curl to bypass Python DNS bugs."""
    if not texts: return []
    
    target_lang = NLLB_LANG_MAP.get(target_lang_code)
    if not target_lang: return texts

    payload = {
        "inputs": texts,
        "parameters": {
            "src_lang": "eng_Latn",
            "tgt_lang": target_lang
        }
    }
    
    payload_json = json.dumps(payload, ensure_ascii=False)
    
    # ✅ Use curl to bypass Python's DNS resolution bugs
    cmd = [
        "curl", "-s", "-w", "\n%{http_code}", "-X", "POST",
        "-H", f"Authorization: Bearer {HF_TOKEN}",
        "-H", "Content-Type: application/json",
        "-d", payload_json,
        API_URL,
        "--max-time", "120",
        "--retry", "5",          # Curl will retry 5 times internally on DNS/Network errors
        "--retry-delay", "5",    # Wait 5 seconds between retries
        "--retry-all-errors"     # Retry on all errors (including DNS)
    ]
    
    try:
        # Run curl. It handles all network retries natively.
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        output = result.stdout.strip()
        
        # The last line is the HTTP status code (because of -w "\n%{http_code}")
        lines = output.rsplit('\n', 1)
        body = lines[0]
        status_code = int(lines[1]) if len(lines) > 1 else 0
        
        if status_code == 200:
            response_data = json.loads(body)
            return [item.get("translation_text", orig) for item, orig in zip(response_data, texts)]
            
        elif status_code == 503:
            print(f"    ⏳ Model loading on HF servers. Waiting 20s and trying one last time...")
            time.sleep(20)
            # One final retry for 503
            result2 = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            output2 = result2.stdout.strip()
            lines2 = output2.rsplit('\n', 1)
            body2 = lines2[0]
            status2 = int(lines2[1]) if len(lines2) > 1 else 0
            if status2 == 200:
                response_data = json.loads(body2)
                return [item.get("translation_text", orig) for item, orig in zip(response_data, texts)]
            else:
                print(f"    ⚠️ Model still loading. Leaving this chunk in English.")
                return texts
        else:
            print(f"    ⚠️ HF API Error {status_code}: {body[:100]}")
            return texts
            
    except subprocess.TimeoutExpired:
        print(f"    ⏱️ Curl timed out after 5 minutes. Leaving this chunk in English.")
        return texts
    except Exception as e:
        print(f"    ⚠️ Unexpected error: {e}")
        return texts

# ----------------------------------------------------------------------
# HTML PARSING & EXTRACTION
# ----------------------------------------------------------------------
def extract_and_translate_page(soup, target_lang):
    texts_to_translate = []
    elements_map = [] 
    
    if soup.title and soup.title.string:
        texts_to_translate.append(soup.title.string.strip())
        elements_map.append(('title', soup.title))
        
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        texts_to_translate.append(meta_desc['content'].strip())
        elements_map.append(('meta_desc', meta_desc))
        
    for prop in ['og:title', 'og:description', 'twitter:title', 'twitter:description']:
        tag = soup.find('meta', attrs={'property': prop}) or soup.find('meta', attrs={'name': prop})
        if tag and tag.get('content'):
            texts_to_translate.append(tag['content'].strip())
            elements_map.append((f'meta_{prop}', tag))

    for img in soup.find_all('img', alt=True):
        if img['alt'].strip() and not img['alt'].startswith('http'):
            texts_to_translate.append(img['alt'].strip())
            elements_map.append(('img_alt', img))

    ignore_tags = {'script', 'style', 'code', 'pre', 'svg', 'math'}
    for text_node in soup.find_all(string=True):
        if isinstance(text_node, Comment): continue
        parent = text_node.parent
        if parent.name in ignore_tags: continue
        
        in_head = False
        curr = parent
        while curr and curr.name:
            if curr.name == 'head': in_head = True; break
            curr = curr.parent
        if in_head: continue

        original = str(text_node).strip()
        if len(original) > 2: 
            texts_to_translate.append(original)
            elements_map.append(('text_node', text_node))

    print(f"    🧠 Sending {len(texts_to_translate)} strings to Meta NLLB-200...")
    
    # Send in chunks of 15 to avoid API payload size limits
    translated_texts = []
    chunk_size = 15
    total_chunks = (len(texts_to_translate) + chunk_size - 1) // chunk_size
    
    for i in range(0, len(texts_to_translate), chunk_size):
        chunk = texts_to_translate[i:i + chunk_size]
        chunk_num = (i // chunk_size) + 1
        print(f"    ⏳ Chunk {chunk_num}/{total_chunks}...")
        
        translated_chunk = translate_batch_with_nllb(chunk, target_lang)
        translated_texts.extend(translated_chunk)
    
    if len(translated_texts) == len(elements_map):
        for i, (elem_type, elem) in enumerate(elements_map):
            new_text = translated_texts[i]
            if elem_type == 'title': elem.string = new_text
            elif elem_type.startswith('meta_'): elem['content'] = new_text
            elif elem_type == 'img_alt': elem['alt'] = new_text
            elif elem_type == 'text_node': elem.replace_with(new_text)
    else:
        print(f"    ❌ AI returned mismatched array length. Skipping injection.")
        
    return soup

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
            subprocess.run(["git", "commit", "-m", f"translate-nllb({target_lang}): batch ({len(file_paths)} files)"], check=False, capture_output=True)
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

    print(f"🚀 Translating to {target} using Meta NLLB-200 (High Quality)")

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

            soup = extract_and_translate_page(soup, target)
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
                
        except Exception as e:
            print(f"  ❌ Error processing {rel}: {e}")

    if batch: git_commit_and_push(target, batch)
    print(f"✅ Done: translated {translated}, skipped {skipped} for {target}")

if __name__ == "__main__":
    main()
