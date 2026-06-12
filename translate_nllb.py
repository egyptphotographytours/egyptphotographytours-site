import os
import subprocess
import torch
from bs4 import BeautifulSoup
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

# --- CONFIGURATION ---
DOMAIN = "https://www.egyptphotographytours.com"

LANGUAGES = {
    'es': 'spa_Latn', 'fr': 'fra_Latn', 'de': 'deu_Latn', 'it': 'ita_Latn',
    'pt': 'por_Latn', 'ru': 'rus_Cyrl', 'ja': 'jpn_Jpan', 'zh-CN': 'zho_Hans',
    'ko': 'kor_Hang', 'ar': 'arb_Arab', 'hi': 'hin_Deva', 'nl': 'nld_Latn',
    'sv': 'swe_Latn', 'pl': 'pol_Latn', 'tr': 'tur_Latn', 'vi': 'vie_Latn',
    'th': 'tha_Thai', 'id': 'ind_Latn', 'cs': 'ces_Latn', 'ro': 'ron_Latn',
    'tl': 'tgl_Latn', 'no': 'nob_Latn', 'da': 'dan_Latn', 'fi': 'fin_Latn'
}

def get_changed_files():
    """Return list of files changed in the last commit (relative paths)."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'],
            capture_output=True, text=True, check=True
        )
        files = [f.strip() for f in result.stdout.split('\n') if f.strip()]
        return files
    except:
        # If git diff fails (e.g., first commit), translate everything
        return ['FORCE_FULL_RUN']

def translate_text(text, tokenizer, model, target_code):
    """Translate a single text chunk using NLLB."""
    if not text or len(text.strip()) <= 2:
        return text
    try:
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            translated_tokens = model.generate(
                **inputs,
                forced_bos_token_id=tokenizer.lang_code_to_id[target_code],
                max_length=512
            )
        translated = tokenizer.batch_decode(translated_tokens, skip_special_tokens=True)[0]
        return translated if translated.strip() else text
    except Exception as e:
        print(f"⚠️ Translation error: {e}")
        return text

def translate_soup(soup, tokenizer, model, target_code):
    """Translate title, meta description, and all text inside body (by block)."""
    # Set HTML language attribute
    if soup.html:
        soup.html['lang'] = target_code.split('_')[0]  # e.g., 'spa_Latn' -> 'spa'

    # Translate <title>
    if soup.title and soup.title.string:
        soup.title.string = translate_text(soup.title.string.strip(), tokenizer, model, target_code)

    # Translate meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        meta_desc['content'] = translate_text(meta_desc['content'].strip(), tokenizer, model, target_code)

    # Translate body text – by paragraph/block for speed & context
    if soup.body:
        for element in soup.body.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'span', 'div']):
            if element.string and element.string.strip():
                original = element.string.strip()
                translated = translate_text(original, tokenizer, model, target_code)
                if translated != original:
                    element.string = translated

    return soup

def add_hreflang_tags(soup, src_rel_path):
    """Insert hreflang alternate links (SEO)."""
    # Remove existing alternates
    for old in soup.find_all('link', rel='alternate'):
        old.decompose()

    # Add for each language
    for lang in LANGUAGES:
        if lang == 'en':
            href = f"{DOMAIN}/{src_rel_path}"
        else:
            href = f"{DOMAIN}/{lang}/{src_rel_path}"
        tag = soup.new_tag('link', rel='alternate', hreflang=lang, href=href)
        if soup.head:
            soup.head.append(tag)

    # x-default
    default_tag = soup.new_tag('link', rel='alternate', hreflang='x-default', href=f"{DOMAIN}/{src_rel_path}")
    if soup.head:
        soup.head.append(default_tag)

    return soup

def main():
    target_lang = os.getenv('TARGET_LANG')
    if not target_lang or target_lang not in LANGUAGES:
        print(f"❌ Invalid TARGET_LANG: {target_lang}")
        return

    target_code = LANGUAGES[target_lang]
    print(f"🚀 Starting translation to {target_lang} (code: {target_code})")

    # Load model (only once per job)
    print("🧠 Loading NLLB model...")
    model_name = "facebook/nllb-200-distilled-600M"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
    model.eval()  # inference mode
    # Limit CPU threads to avoid overloading runner
    torch.set_num_threads(2)
    print("✅ Model loaded")

    # Get changed files from last commit
    changed_files = get_changed_files()
    print(f"📝 Changed files: {changed_files[:5]}..." if len(changed_files) > 5 else f"📝 Changed files: {changed_files}")

    # Prepare output directory
    out_root = f"./{target_lang}"
    os.makedirs(out_root, exist_ok=True)

    # Walk through all HTML files (skip language folders)
    ignore_folders = set(LANGUAGES.keys()) | {'.git', '.github', '__pycache__', 'node_modules'}
    source_files = []
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in ignore_folders and not d.startswith('.')]
        for file in files:
            if file.endswith('.html'):
                source_files.append(os.path.join(root, file))

    print(f"🔍 Found {len(source_files)} HTML files to consider")

    translated_count = 0
    for src_path in source_files:
        # Normalize relative path (remove leading './')
        rel_path = src_path[2:] if src_path.startswith('./') else src_path
        out_path = os.path.join(out_root, rel_path)

        # Determine if translation is needed
        needs_translation = (
            not os.path.exists(out_path) or
            rel_path in changed_files or
            'FORCE_FULL_RUN' in changed_files
        )

        if not needs_translation:
            continue

        print(f"  🔄 Translating: {rel_path}")
        try:
            with open(src_path, 'r', encoding='utf-8') as f:
                html_content = f.read()

            soup = BeautifulSoup(html_content, 'html.parser')
            soup = translate_soup(soup, tokenizer, model, target_code)

            # For href construction, remove 'index.html' to get clean URL path
            href_path = rel_path.replace('index.html', '')
            soup = add_hreflang_tags(soup, href_path)

            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))

            translated_count += 1
        except Exception as e:
            print(f"  ❌ Error translating {rel_path}: {e}")

    print(f"✅ Finished! Translated {translated_count} files to {target_lang}.")

if __name__ == "__main__":
    main()
