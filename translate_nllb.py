import os
import subprocess
import shutil # 🧹 Added for automatic folder deletion
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

TARGET_LANG = os.getenv('TARGET_LANG')
TARGET_NLLB_CODE = LANGUAGES[TARGET_LANG]

print(f"🧠 Loading Meta NLLB AI Model for {TARGET_LANG}...")
MODEL_NAME = "facebook/nllb-200-distilled-600M"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)

def translate_text(text):
    if not text or len(text.strip()) <= 2: return text
    try:
        inputs = tokenizer(text, return_tensors="pt")
        translated_tokens = model.generate(
            **inputs,
            forced_bos_token_id=tokenizer.lang_code_to_id[TARGET_NLLB_CODE],
            max_length=512
        )
        translated_text = tokenizer.batch_decode(translated_tokens, skip_special_tokens=True)[0]
        return translated_text if translated_text.strip() else text
    except Exception as e:
        print(f"⚠️ Error translating: {e}")
        return text

def get_changed_files():
    try:
        result = subprocess.run(['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'], capture_output=True, text=True, check=True)
        return result.stdout.strip().split('\n')
    except:
        return ['FORCE_FULL_RUN'] 

def main():
    changed_files = get_changed_files()
    
    # 🧹 THE MAGIC AUTO-CLEAN STEP
    # Before doing anything, completely delete the target language folder if it exists.
    # This wipes out any broken English files or messy nested folders automatically!
    target_folder = f'./{TARGET_LANG}'
    if os.path.exists(target_folder):
        print(f"🧹 Auto-cleaning old/broken files in {target_folder}...")
        shutil.rmtree(target_folder)
        
    # Also clean up the stray folders in the root (ms, la, zh) that caused the mess
    # We use try/except because 24 jobs might try to delete them at the exact same millisecond
    stray_folders = ['./ms', './la', './zh']
    for stray in stray_folders:
        try:
            if os.path.exists(stray):
                print(f"🧹 Removing stray root folder: {stray}")
                shutil.rmtree(stray)
        except Exception:
            pass 

    # 🛡️ BULLETPROOF FOLDER IGNORING
    IGNORE_FOLDERS = set(LANGUAGES.keys())
    IGNORE_FOLDERS.update(['zh', 'ms', 'la', 'en', 'tl', 'no', 'da', 'fi', '.git', '.github', '__pycache__', 'node_modules'])

    source_files = []
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in IGNORE_FOLDERS and not d.startswith('.')]
        for file in files:
            if file.endswith('.html'):
                source_files.append(os.path.join(root, file))

    print(f"🚀 Checking {len(source_files)} source files for {TARGET_LANG}...")
    
    translated_count = 0
    for src_path in source_files:
        out_path = os.path.join(f'./{TARGET_LANG}', src_path)
        
        # Because we deleted the folder above, this will now ALWAYS be True for a fresh start
        needs_translation = (not os.path.exists(out_path)) or (src_path in changed_files) or ('FORCE_FULL_RUN' in changed_files)
        
        if needs_translation:
            print(f"  🔄 Translating: {src_path} -> {out_path}")
            with open(src_path, 'r', encoding='utf-8') as f:
                html_content = f.read()

            soup = BeautifulSoup(html_content, 'html.parser')
            
            if soup.html: soup.html['lang'] = TARGET_LANG
            
            if soup.title and soup.title.string:
                soup.title.string = translate_text(soup.title.string)
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                meta_desc['content'] = translate_text(meta_desc['content'])
                
            if soup.body:
                for text_node in soup.body.find_all(text=True):
                    parent = text_node.parent
                    if parent and parent.name in ['script', 'style', 'code', 'pre', 'svg', 'path']:
                        continue
                    
                    text = str(text_node).strip()
                    if len(text) > 2:
                        translated = translate_text(text)
                        if translated != text:
                            text_node.replace_with(translated)
                            
            for old_tag in soup.find_all('link', rel='alternate'):
                old_tag.decompose()
                
            for lang in LANGUAGES:
                href_path = src_path.replace('./', '').replace('index.html', '')
                if lang == 'en': 
                    href = f"{DOMAIN}/{href_path}"
                else:
                    href = f"{DOMAIN}/{lang}/{href_path}"
                
                tag = soup.new_tag('link', rel='alternate', hreflang=lang, href=href)
                if soup.head: soup.head.append(tag)
                
            href_path = src_path.replace('./', '').replace('index.html', '')
            default_tag = soup.new_tag('link', rel='alternate', hreflang='x-default', href=f"{DOMAIN}/{href_path}")
            if soup.head: soup.head.append(default_tag)

            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            translated_count += 1

    print(f"✅ Finished! Translated {translated_count} files to {TARGET_LANG}.")

if __name__ == "__main__":
    main()
