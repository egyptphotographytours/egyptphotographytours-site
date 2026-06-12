import os
import subprocess
import torch
from bs4 import BeautifulSoup
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

# --- CONFIGURATION ---
DOMAIN = "https://www.egyptphotographytours.com"

# The 24 languages we are targeting (ISO Code: Meta NLLB Code)
LANGUAGES = {
    'es': 'spa_Latn', 'fr': 'fra_Latn', 'de': 'deu_Latn', 'it': 'ita_Latn',
    'pt': 'por_Latn', 'ru': 'rus_Cyrl', 'ja': 'jpn_Jpan', 'zh-CN': 'zho_Hans',
    'ko': 'kor_Hang', 'ar': 'arb_Arab', 'hi': 'hin_Deva', 'nl': 'nld_Latn',
    'sv': 'swe_Latn', 'pl': 'pol_Latn', 'tr': 'tur_Latn', 'vi': 'vie_Latn',
    'th': 'tha_Thai', 'id': 'ind_Latn', 'cs': 'ces_Latn', 'ro': 'ron_Latn',
    'tl': 'tgl_Latn', 'no': 'nob_Latn', 'da': 'dan_Latn', 'fi': 'fin_Latn'
}

TARGET_LANG = os.getenv('TARGET_LANG')
TARGET_NLLB_CODE = LANGUAGES[TARGET_LANG]

print(f"🧠 Loading Meta NLLB AI Model for {TARGET_LANG}...")
# We use the 600M distilled model: it's fast, free, and fits perfectly in GitHub's free servers
MODEL_NAME = "facebook/nllb-200-distilled-600M"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)

def translate_text(text):
    """Translates a single piece of text using the AI."""
    if not text or not text.strip(): return text
    try:
        inputs = tokenizer(text, return_tensors="pt")
        translated_tokens = model.generate(
            **inputs,
            forced_bos_token_id=tokenizer.lang_code_to_id[TARGET_NLLB_CODE],
            max_length=512
        )
        return tokenizer.batch_decode(translated_tokens, skip_special_tokens=True)[0]
    except Exception as e:
        print(f"Error translating: {e}")
        return text

def get_changed_files():
    """Checks Git to see exactly which files you changed recently."""
    try:
        result = subprocess.run(['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'], capture_output=True, text=True, check=True)
        return result.stdout.strip().split('\n')
    except:
        # If it's the very first commit, it forces a full translation of everything
        return ['FORCE_FULL_RUN'] 

def main():
    changed_files = get_changed_files()
    
    # 1. Find all your original English HTML files (ignoring the translated folders)
    source_files = []
    for root, dirs, files in os.walk('.'):
        # Skip hidden folders, cache, and the language folders we create
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in LANGUAGES and d != '__pycache__']
        for file in files:
            if file.endswith('.html'):
                source_files.append(os.path.join(root, file))

    print(f"🚀 Checking {len(source_files)} source files for {TARGET_LANG}...")
    
    translated_count = 0
    for src_path in source_files:
        # Determine where the translated file should go (e.g., './about.html' -> './es/about.html')
        out_path = os.path.join(f'./{TARGET_LANG}', src_path)
        
        # THE SMART LOGIC: 
        # Translate if the translated file DOES NOT EXIST yet (first run or new language) 
        # OR if the source file was CHANGED in your last commit.
        needs_translation = (not os.path.exists(out_path)) or (src_path in changed_files) or ('FORCE_FULL_RUN' in changed_files)
        
        if needs_translation:
            print(f"  🔄 Translating: {src_path} -> {out_path}")
            with open(src_path, 'r', encoding='utf-8') as f:
                html_content = f.read()

            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Update the HTML language tag
            if soup.html: soup.html['lang'] = TARGET_LANG
            
            # Translate SEO Title and Meta Description
            if soup.title and soup.title.string:
                soup.title.string = translate_text(soup.title.string)
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                meta_desc['content'] = translate_text(meta_desc['content'])
                
            # Translate body text safely (preserves your links and bold tags)
            for element in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'a', 'span', 'td', 'th', 'label', 'button']):
                if element.string and element.string.strip():
                    element.string.replace_with(translate_text(element.string.strip()))
                    
            # Remove old hreflang tags to prevent duplicates
            for old_tag in soup.find_all('link', rel='alternate'):
                old_tag.decompose()
                
            # Inject perfect SEO Hreflang tags for all 24 languages
            for lang in LANGUAGES:
                href_path = src_path.replace('./', '').replace('index.html', '')
                if lang == 'en': # Assuming English is your default root language
                    href = f"{DOMAIN}/{href_path}"
                else:
                    href = f"{DOMAIN}/{lang}/{href_path}"
                
                tag = soup.new_tag('link', rel='alternate', hreflang=lang, href=href)
                if soup.head: soup.head.append(tag)
                
            # Add the 'x-default' tag for Google
            href_path = src_path.replace('./', '').replace('index.html', '')
            default_tag = soup.new_tag('link', rel='alternate', hreflang='x-default', href=f"{DOMAIN}/{href_path}")
            if soup.head: soup.head.append(default_tag)

            # Save the new translated file
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            translated_count += 1

    print(f"✅ Finished! Translated {translated_count} files to {TARGET_LANG}.")

if __name__ == "__main__":
    main()
