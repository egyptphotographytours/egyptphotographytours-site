import os
import sys
import time
import requests
from bs4 import BeautifulSoup

DOMAIN = "https://www.egyptphotographytours.com"

# All target languages (folder names)
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

def wait_for_server():
    """Wait for LibreTranslate server to become fully responsive."""
    max_attempts = 60
    for i in range(max_attempts):
        try:
            resp = requests.get("http://localhost:5000/languages", timeout=5)
            if resp.status_code == 200:
                print("✅ LibreTranslate server is ready")
                return True
        except:
            pass
        print(f"⏳ Waiting for server ({i+1}/{max_attempts})...")
        time.sleep(2)
    print("❌ Server never became ready")
    return False

def translate_text(text, target_lang, retries=5):
    """Translate a single text chunk with exponential backoff."""
    if not text or len(text.strip()) < 3:
        return text

    url = "http://localhost:5000/translate"
    payload = {
        "q": text,
        "source": "en",
        "target": target_lang,
        "format": "text"
    }

    for attempt in range(retries):
        try:
            response = requests.post(url, json=payload, timeout=120)
            if response.status_code == 200:
                return response.json()["translatedText"]
            else:
                print(f"    API HTTP {response.status_code}")
        except requests.exceptions.ConnectionError as e:
            print(f"    Connection error (attempt {attempt+1}/{retries}): {e}")
        except Exception as e:
            print(f"    Error (attempt {attempt+1}/{retries}): {e}")

        # Exponential backoff: 3, 6, 12, 24, 48 seconds
        if attempt < retries - 1:
            sleep_time = 3 * (2 ** attempt)
            print(f"    Retrying in {sleep_time}s...")
            time.sleep(sleep_time)

    return text  # fallback

def translate_soup(soup, target_lang):
    """Translate all relevant text in the HTML soup."""
    if soup.title and soup.title.string:
        original = soup.title.string.strip()
        soup.title.string = translate_text(original, target_lang)

    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        original = meta_desc['content'].strip()
        meta_desc['content'] = translate_text(original, target_lang)

    # Translate body text (only text nodes inside these tags)
    if soup.body:
        for elem in soup.body.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'div', 'span', 'a']):
            if elem.string and elem.string.strip():
                original = elem.string.strip()
                translated = translate_text(original, target_lang)
                if translated != original:
                    elem.string = translated
    return soup

def add_hreflang_tags(soup, rel_path):
    """Add hreflang alternate links for SEO."""
    for old in soup.find_all('link', rel='alternate'):
        old.decompose()

    for lang in TARGET_LANGS + ['en']:
        href = f"{DOMAIN}/{lang}/{rel_path}"
        tag = soup.new_tag('link', rel='alternate', hreflang=lang, href=href)
        if soup.head:
            soup.head.append(tag)

    default_tag = soup.new_tag('link', rel='alternate', hreflang='x-default', href=f"{DOMAIN}/{rel_path}")
    if soup.head:
        soup.head.append(default_tag)
    return soup

def main():
    target = os.getenv('TARGET_LANG')
    if not target or target not in TARGET_LANGS:
        print(f"❌ Invalid target: {target}")
        return

    print(f"🚀 Translating to: {target}")

    # Wait for server before doing anything else
    if not wait_for_server():
        sys.exit(1)

    changed = get_changed_files()
    print(f"📝 Changed files: {changed[:5]}{'...' if len(changed)>5 else ''}")

    out_dir = f"./{target}"
    os.makedirs(out_dir, exist_ok=True)

    # Collect all HTML files (ignore language folders)
    ignore_folders = set(TARGET_LANGS) | {'en', '.git', '.github', '__pycache__', 'node_modules'}
    source_files = []

    for file in os.listdir('.'):
        if file.endswith('.html') and os.path.isfile(file):
            source_files.append(file)

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

            soup = translate_soup(soup, target)

            href_path = rel.replace('index.html', '')
            soup = add_hreflang_tags(soup, href_path)

            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            translated += 1
        except Exception as e:
            print(f"  ❌ Failed: {e}")

    print(f"✅ Done: translated {translated}, skipped {skipped} for {target}")

if __name__ == "__main__":
    main()
