import os
import sys
import time
import requests
from bs4 import BeautifulSoup

DOMAIN = "https://www.egyptphotographytours.com"

# List of target languages as folder names
TARGET_LANGS = ['es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'zh-CN', 'ko', 'ar',
                'hi', 'nl', 'sv', 'pl', 'tr', 'vi', 'th', 'id', 'cs', 'ro', 'tl', 'no', 'da', 'fi']

def get_changed_files():
    """Return list of files changed in the last commit."""
    try:
        import subprocess
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'],
            capture_output=True, text=True, check=True
        )
        return [f.strip() for f in result.stdout.split('\n') if f.strip()]
    except:
        return ['FORCE_FULL_RUN']

def translate_text(text, source_lang, target_lang, retries=3):
    """Translate a single text chunk using LibreTranslate API."""
    url = "http://localhost:5000/translate"
    headers = {"Content-Type": "application/json"}
    payload = {
        "q": text,
        "source": source_lang,
        "target": target_lang,
        "format": "text"
    }

    for attempt in range(retries):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            if response.status_code == 200:
                return response.json()["translatedText"]
            else:
                print(f"    API Error: {response.status_code}")
                time.sleep(2)
        except Exception as e:
            print(f"    Attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return text

def translate_soup(soup, target_lang_code):
    """Translate all relevant text in the HTML soup."""
    # Translate title
    if soup.title and soup.title.string:
        soup.title.string = translate_text(soup.title.string.strip(), "en", target_lang_code)

    # Translate meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        meta_desc['content'] = translate_text(meta_desc['content'].strip(), "en", target_lang_code)

    # Translate text in body elements
    if soup.body:
        for elem in soup.body.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'div', 'span', 'a']):
            if elem.string and elem.string.strip():
                original = elem.string.strip()
                translated = translate_text(original, "en", target_lang_code)
                if translated != original:
                    elem.string = translated
    return soup

def add_hreflang_tags(soup, rel_path):
    """Add proper hreflang links for SEO."""
    # Remove existing alternate links
    for old in soup.find_all('link', rel='alternate'):
        old.decompose()

    # Add tags for all languages
    for lang in TARGET_LANGS + ['en']:
        href = f"{DOMAIN}/{lang}/{rel_path}"
        tag = soup.new_tag('link', rel='alternate', hreflang=lang, href=href)
        if soup.head:
            soup.head.append(tag)

    # x-default tag
    default_tag = soup.new_tag('link', rel='alternate', hreflang='x-default', href=f"{DOMAIN}/{rel_path}")
    if soup.head:
        soup.head.append(default_tag)
    return soup

def main():
    target_lang = os.getenv('TARGET_LANG')
    if not target_lang or target_lang not in TARGET_LANGS:
        print(f"❌ Invalid target language: {target_lang}")
        return

    print(f"🚀 Translating to: {target_lang}")

    # Wait for LibreTranslate server to be ready
    max_retries = 30
    for i in range(max_retries):
        try:
            response = requests.get("http://localhost:5000/languages", timeout=5)
            if response.status_code == 200:
                print("✅ LibreTranslate server is ready")
                break
        except:
            print(f"⏳ Waiting for server (attempt {i+1}/{max_retries})...")
            time.sleep(2)

    # Get changed files
    changed_files = get_changed_files()
    print(f"📝 Changed files: {changed_files[:5]}...")

    # Prepare output directory
    out_dir = f"./{target_lang}"
    os.makedirs(out_dir, exist_ok=True)

    # Find all HTML files
    ignore_folders = set(TARGET_LANGS) | {'en', '.git', '.github', '__pycache__', 'node_modules'}
    source_files = []

    # Root files
    for file in os.listdir('.'):
        if file.endswith('.html') and os.path.isfile(file):
            source_files.append(file)

    # Subdirectories
    for root, dirs, files in os.walk('.'):
        if root == '.':
            dirs[:] = [d for d in dirs if d not in ignore_folders]
            continue
        for file in files:
            if file.endswith('.html'):
                full_path = os.path.join(root, file)
                source_files.append(full_path)

    print(f"🔍 Found {len(source_files)} HTML files to process")
    translated = 0
    skipped = 0

    for src_path in source_files:
        rel_path = src_path[2:] if src_path.startswith('./') else src_path
        out_path = os.path.join(out_dir, rel_path)

        # Skip if unchanged
        if os.path.exists(out_path) and rel_path not in changed_files and 'FORCE_FULL_RUN' not in changed_files:
            skipped += 1
            continue

        print(f"  🔄 Processing: {rel_path}")
        try:
            with open(src_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f.read(), 'html.parser')

            soup = translate_soup(soup, target_lang)

            href_path = rel_path.replace('index.html', '')
            soup = add_hreflang_tags(soup, href_path)

            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            translated += 1
        except Exception as e:
            print(f"    ❌ Error: {e}")

    print(f"✅ Done: translated {translated}, skipped {skipped} files for {target_lang}")

if __name__ == "__main__":
    main()
