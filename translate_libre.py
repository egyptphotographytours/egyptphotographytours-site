import os
import sys
import time
import requests
from bs4 import BeautifulSoup

# Force real-time output (no buffering)
sys.stdout.reconfigure(line_buffering=True)

DOMAIN = "https://www.egyptphotographytours.com"

TARGET_LANGS = ['es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'zh-CN', 'ko', 'ar',
                'hi', 'nl', 'sv', 'pl', 'tr', 'vi', 'th', 'id', 'cs', 'ro', 'tl', 'no', 'da', 'fi']

def get_changed_files():
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
    """Wait up to 60 seconds for server to respond."""
    print("⏳ Checking if LibreTranslate server is ready...")
    for i in range(12):   # 12 * 5 = 60 seconds
        try:
            resp = requests.get("http://localhost:5000/languages", timeout=5)
            if resp.status_code == 200:
                print("✅ LibreTranslate server is responsive")
                return True
        except:
            pass
        print(f"   Still waiting... (attempt {i+1}/12)")
        time.sleep(5)
    print("❌ Server did not respond in time")
    return False

def translate_text(text, target_lang, retries=3):
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
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 200:
                return resp.json()["translatedText"]
            else:
                print(f"    HTTP {resp.status_code}")
        except Exception as e:
            print(f"    Translation error (attempt {attempt+1}): {e}")
        if attempt < retries - 1:
            time.sleep(5)
    return text

def translate_soup(soup, target_lang):
    if soup.title and soup.title.string:
        soup.title.string = translate_text(soup.title.string.strip(), target_lang)
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        meta_desc['content'] = translate_text(meta_desc['content'].strip(), target_lang)
    if soup.body:
        for elem in soup.body.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'div', 'span', 'a']):
            if elem.string and elem.string.strip():
                elem.string = translate_text(elem.string.strip(), target_lang)
    return soup

def add_hreflang_tags(soup, rel_path):
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

    if not wait_for_server():
        sys.exit(1)

    changed = get_changed_files()
    print(f"📝 Changed files: {changed[:5]}{'...' if len(changed)>5 else ''}")

    out_dir = f"./{target}"
    os.makedirs(out_dir, exist_ok=True)

    # Ignore all language folders, hidden dirs, and junk
    ignore_folders = set(TARGET_LANGS) | {'en', '.git', '.github', '__pycache__', 'node_modules', 'zh', 'ms', 'la'}
    source_files = []

    # HTML files in root
    for f in os.listdir('.'):
        if f.endswith('.html') and os.path.isfile(f):
            source_files.append(f)

    # HTML files in subdirectories (skip ignored folders)
    for root, dirs, files in os.walk('.'):
        if root == '.':
            dirs[:] = [d for d in dirs if d not in ignore_folders]
            continue
        for f in files:
            if f.endswith('.html'):
                source_files.append(os.path.join(root, f))

    print(f"🔍 Found {len(source_files)} HTML files")
    if not source_files:
        print("❌ No source HTML files found! Check your repository structure.")
        sys.exit(1)

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
            print(f"  ❌ Error: {e}")

    print(f"✅ Done: translated {translated}, skipped {skipped} for {target}")

if __name__ == "__main__":
    main()
