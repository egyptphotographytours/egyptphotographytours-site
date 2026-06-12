import os
import subprocess
import time
import deepl
from bs4 import BeautifulSoup

DOMAIN = "https://www.egyptphotographytours.com"
SOURCE_LANG = "EN"

LANG_MAP = {
    'es': 'ES', 'fr': 'FR', 'de': 'DE', 'it': 'IT', 'pt': 'PT',
    'ru': 'RU', 'ja': 'JA', 'zh-CN': 'ZH', 'ko': 'KO', 'ar': 'AR',
    'hi': 'HI', 'nl': 'NL', 'sv': 'SV', 'pl': 'PL', 'tr': 'TR',
    'vi': 'VI', 'th': 'TH', 'id': 'ID', 'cs': 'CS', 'ro': 'RO',
    'tl': 'TL', 'no': 'NB', 'da': 'DA', 'fi': 'FI'
}

def get_changed_files():
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'],
            capture_output=True, text=True, check=True
        )
        return [f.strip() for f in result.stdout.split('\n') if f.strip()]
    except:
        return ['FORCE_FULL_RUN']

def delete_broken_translations(folder_path):
    if not os.path.exists(folder_path):
        return 0
    deleted = 0
    for root, _, files in os.walk(folder_path):
        for file in files:
            if not file.endswith('.html'):
                continue
            full = os.path.join(root, file)
            try:
                with open(full, 'r', encoding='utf-8') as f:
                    content = f.read()
                if len(content) < 100 or (' the ' in content.lower() and ' el ' not in content.lower()):
                    os.remove(full)
                    deleted += 1
                    print(f"  🗑️ Deleted broken: {full}")
            except:
                os.remove(full)
                deleted += 1
    return deleted

def translate_text(text, translator, target_code, retries=2):
    if not text or len(text.strip()) < 3:
        return text
    for attempt in range(retries):
        try:
            result = translator.translate_text(
                text, source_lang=SOURCE_LANG, target_lang=target_code
            )
            return result.text
        except deepl.exceptions.QuotaExceededException:
            print("    ❌ Quota exceeded! Stopping this job.")
            raise
        except Exception as e:
            print(f"    ⚠️ Translation error (attempt {attempt+1}): {e}")
            time.sleep(2)
    return text

def translate_html(soup, translator, target_code):
    if soup.html:
        soup.html['lang'] = target_code.lower()
    if soup.title and soup.title.string:
        soup.title.string = translate_text(soup.title.string.strip(), translator, target_code)
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        meta_desc['content'] = translate_text(meta_desc['content'].strip(), translator, target_code)
    if soup.body:
        for elem in soup.body.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'div', 'span', 'a']):
            if elem.string and elem.string.strip():
                original = elem.string.strip()
                translated = translate_text(original, translator, target_code)
                if translated != original:
                    elem.string = translated
    return soup

def add_hreflang_tags(soup, rel_path):
    for old in soup.find_all('link', rel='alternate'):
        old.decompose()
    for lang in LANG_MAP:
        if lang == 'en':
            href = f"{DOMAIN}/{rel_path}"
        else:
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
    if not target or target not in LANG_MAP:
        print(f"❌ Invalid target: {target}")
        return

    api_key = os.getenv('DEEPL_API_KEY')
    if not api_key:
        print("❌ Missing DEEPL_API_KEY")
        return

    target_code = LANG_MAP[target]
    print(f"🚀 Translating to {target} (DeepL: {target_code})")

    translator = deepl.Translator(api_key, server_url='https://api-free.deepl.com/v2')
    try:
        translator.translate_text("Test", target_lang="DE")
        print("✅ DeepL ready")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return

    out_folder = f"./{target}"
    deleted = delete_broken_translations(out_folder)
    if deleted:
        print(f"🧹 Deleted {deleted} broken translation files")

    changed = get_changed_files()
    print(f"📝 Changed files: {changed[:5]}{'...' if len(changed)>5 else ''}")

    os.makedirs(out_folder, exist_ok=True)

    # Collect all HTML files from root and subdirectories (skip language folders)
    ignore_dirs = set(LANG_MAP.keys()) | {'.git', '.github', '__pycache__', 'node_modules', 'zh', 'ms', 'la'}
    source_files = []
    
    # Root files
    for file in os.listdir('.'):
        if file.endswith('.html') and os.path.isfile(file):
            source_files.append(file)
    
    # Subdirectories
    for root, dirs, files in os.walk('.'):
        if root == '.':
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            continue
        for file in files:
            if file.endswith('.html'):
                full_path = os.path.join(root, file)
                source_files.append(full_path)
    
    print(f"🔍 Found {len(source_files)} HTML files")
    if len(source_files) == 0:
        print("❌ No source HTML files found. Check debug output above.")
        return

    translated = 0
    skipped = 0

    for src in source_files:
        rel = src if not src.startswith('./') else src[2:]
        out_path = os.path.join(out_folder, rel)

        if os.path.exists(out_path) and rel not in changed and 'FORCE_FULL_RUN' not in changed:
            skipped += 1
            continue

        print(f"  🔄 {rel}")
        try:
            with open(src, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f.read(), 'html.parser')
            soup = translate_html(soup, translator, target_code)
            href_path = rel.replace('index.html', '')
            soup = add_hreflang_tags(soup, href_path)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            translated += 1
        except deepl.exceptions.QuotaExceededException:
            print("❌ DeepL quota exceeded – stopping this language job.")
            break
        except Exception as e:
            print(f"  ❌ Error: {e}")

    print(f"✅ Done: translated {translated}, skipped {skipped} (unchanged) for {target}")

if __name__ == "__main__":
    main()
