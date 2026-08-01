import os
import re
import time
import subprocess
from bs4 import BeautifulSoup, Comment, NavigableString
from deep_translator import GoogleTranslator
from datetime import datetime

DOMAIN = "https://www.egyptphotographytours.com"
TARGET_LANGS = [
    'ar', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'zh-CN', 'ko', 
    'hi', 'nl', 'sv', 'pl', 'tr', 'vi', 'th', 'id', 'cs', 'ro', 
    'tl', 'no', 'da', 'fi'
]
IGNORE_TAGS = {'script', 'style', 'code', 'pre', 'svg', 'math', 'noscript', 'iframe', 'template'}
DELIMITER = " [|||] "

LANG_META = {
    'en': {'flag': '🇺🇸', 'name': 'English'},
    'es': {'flag': '🇪🇸', 'name': 'Español'}, 'fr': {'flag': '🇫🇷', 'name': 'Français'},
    'de': {'flag': '🇩🇪', 'name': 'Deutsch'}, 'it': {'flag': '🇮🇹', 'name': 'Italiano'},
    'pt': {'flag': '🇵🇹', 'name': 'Português'}, 'ru': {'flag': '🇷🇺', 'name': 'Русский'},
    'ja': {'flag': '🇯🇵', 'name': '日本語'}, 'zh-CN': {'flag': '🇨🇳', 'name': '中文 (简体)'},
    'ko': {'flag': '🇰🇷', 'name': '한국어'}, 'ar': {'flag': '🇸🇦', 'name': 'العربية'},
    'hi': {'flag': '🇮🇳', 'name': 'हिन्दी'}, 'nl': {'flag': '🇳🇱', 'name': 'Nederlands'},
    'sv': {'flag': '🇸🇪', 'name': 'Svenska'}, 'pl': {'flag': '🇵🇱', 'name': 'Polski'},
    'tr': {'flag': '🇹🇷', 'name': 'Türkçe'}, 'vi': {'flag': '🇻🇳', 'name': 'Tiếng Việt'},
    'th': {'flag': '🇹🇭', 'name': 'ไทย'}, 'id': {'flag': '🇮🇩', 'name': 'Bahasa Indonesia'},
    'cs': {'flag': '🇨🇿', 'name': 'Čeština'}, 'ro': {'flag': '🇷🇴', 'name': 'Română'},
    'tl': {'flag': '🇵🇭', 'name': 'Filipino'}, 'no': {'flag': '🇳🇴', 'name': 'Norsk'},
    'da': {'flag': '🇩🇰', 'name': 'Dansk'}, 'fi': {'flag': '🇫🇮', 'name': 'Suomi'}
}

def get_relative_url(lang_code, base_path):
    clean_path = base_path.replace('index.html', '').replace('.html', '')
    if lang_code == 'en':
        return f"/{clean_path}" if clean_path else "/"
    else:
        return f"/{lang_code}/{clean_path}" if clean_path else f"/{lang_code}/"

def get_changed_english_files():
    """Detects which English files were modified in the latest Git push."""
    try:
        result = subprocess.run(['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'], capture_output=True, text=True, check=True)
        changed_files = result.stdout.strip().split('\n')
        return [f for f in changed_files if f.endswith('.html') and not any(f.startswith(lang + '/') for lang in TARGET_LANGS) and os.path.exists(f)]
    except:
        return []

# ==========================================
# 1. DOM FIREWALL TRANSLATION
# ==========================================
def safe_translate(texts, target_lang):
    if not texts: return []
    translator = GoogleTranslator(source='en', target=target_lang)
    translated_texts = []
    chunks, current_chunk, current_len = [], [], 0
    
    for t in texts:
        add_len = len(t) + len(DELIMITER)
        if current_len + add_len > 4500 and current_chunk:
            chunks.append(current_chunk)
            current_chunk, current_len = [], 0
        current_chunk.append(t)
        current_len += add_len
    if current_chunk: chunks.append(current_chunk)
        
    for chunk in chunks:
        payload = DELIMITER.join(chunk)
        try:
            res = translator.translate(payload)
            if res:
                parts = res.split(DELIMITER)
                if len(parts) == len(chunk): translated_texts.extend(parts)
                else:
                    for t in chunk:
                        try: translated_texts.append(translator.translate(t) or t); time.sleep(0.1)
                        except: translated_texts.append(t)
            else: translated_texts.extend(chunk)
        except Exception:
            for t in chunk:
                try: translated_texts.append(translator.translate(t) or t); time.sleep(0.2)
                except: translated_texts.append(t)
        time.sleep(0.5)
    return translated_texts

def extract_and_translate(soup, target_lang):
    texts, nodes = [], []
    if soup.title and soup.title.string:
        texts.append(soup.title.string.strip())
        nodes.append(('title', soup.title))
        
    for meta_name in ['description', 'og:title', 'og:description', 'twitter:title', 'twitter:description']:
        tag = soup.find('meta', attrs={'name': meta_name}) or soup.find('meta', attrs={'property': meta_name})
        if tag and tag.get('content'):
            texts.append(tag['content'].strip())
            nodes.append(('meta', tag))
            
    for img in soup.find_all('img', alt=True):
        if img['alt'].strip() and not img['alt'].startswith('http'):
            texts.append(img['alt'].strip())
            nodes.append(('alt', img))
            
    for text_node in soup.find_all(string=True):
        if isinstance(text_node, Comment): continue
        curr = text_node.parent
        skip = False
        while curr:
            if curr.name in IGNORE_TAGS: skip = True; break
            if curr.get('translate') == 'no': skip = True; break
            if 'notranslate' in curr.get('class', []): skip = True; break
            if curr.name == 'head': skip = True; break
            curr = curr.parent
        if not skip:
            original = str(text_node).strip()
            if len(original) > 2 and not original.isspace():
                texts.append(original)
                nodes.append(('text', text_node))

    if texts:
        translated_texts = safe_translate(texts, target_lang)
        if len(translated_texts) == len(nodes):
            for i, (node_type, node) in enumerate(nodes):
                new_text = translated_texts[i]
                if node_type == 'title': node.string = new_text
                elif node_type == 'meta': node['content'] = new_text
                elif node_type == 'alt': node['alt'] = new_text
                elif node_type == 'text': node.replace_with(NavigableString(new_text))
    return soup

# ==========================================
# 2. LINK FIXER & SMART MENU BUILDER
# ==========================================
def fix_internal_links(soup, target_lang):
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith(('http', 'mailto:', 'tel:', 'javascript:', '#', '//')): continue
        if re.search(r'\.(jpg|jpeg|png|gif|svg|webp|css|js|pdf|zip|mp4|webm|ico)(\?|$)', href, re.I): continue
        
        has_lang_prefix = any(href.startswith(f"/{lang}/") or href == f"/{lang}" for lang in TARGET_LANGS)
        if has_lang_prefix: continue
        
        if href.startswith('/'):
            a['href'] = f"/{target_lang}{href}" if href != '/' else f"/{target_lang}/"
        else:
            clean = href.replace('.html', '')
            a['href'] = f"/{target_lang}/{clean}"
    return soup

def inject_dynamic_lang_menu(soup, target_lang, base_path):
    lang_menu = soup.find('div', id='lang-menu')
    if not lang_menu: return soup

    for old_link in lang_menu.find_all('a', class_='lang-item'):
        old_link.decompose()

    en_url = get_relative_url('en', base_path)
    is_active = "is-active" if target_lang == 'en' else ""
    en_html = f'<a href="{en_url}" class="lang-item {is_active}" role="menuitem"><span class="lang-flag" aria-hidden="true">🇺🇸</span><span class="lang-name">English</span></a>'
    lang_menu.append(BeautifulSoup(en_html, 'lxml'))

    for lang in TARGET_LANGS:
        if lang == 'en': continue
        if os.path.exists(os.path.join(lang, base_path)):
            lang_url = get_relative_url(lang, base_path)
            is_active = "is-active" if target_lang == lang else ""
            flag = LANG_META[lang]['flag']
            name = LANG_META[lang]['name']
            link_html = f'<a href="{lang_url}" class="lang-item {is_active}" role="menuitem"><span class="lang-flag" aria-hidden="true">{flag}</span><span class="lang-name">{name}</span></a>'
            lang_menu.append(BeautifulSoup(link_html, 'lxml'))
    return soup

# ==========================================
# 3. GLOBAL SEO & SITEMAP GENERATOR
# ==========================================
def inject_global_seo_and_sitemap():
    print("🔗 Updating Language Menus, SEO Tags & Generating Sitemap...")
    page_map = {}
    
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['scripts', 'node_modules', '.github']]
        for f in files:
            if f.endswith('.html'):
                rel = os.path.relpath(os.path.join(root, f), '.')
                base = rel
                lang_code = 'en'
                for lang in TARGET_LANGS:
                    if rel.startswith(f"{lang}/"):
                        base = rel[len(f"{lang}/"):]
                        lang_code = lang
                        break
                if base not in page_map: page_map[base] = {}
                page_map[base][lang_code] = rel

    for base, langs in page_map.items():
        for lang_code, rel_path in langs.items():
            with open(rel_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'lxml')
                
            for old in soup.find_all('link', rel='alternate'): old.decompose()
            for old in soup.find_all('link', rel='canonical'): old.decompose()
            
            head = soup.find('head')
            if not head: continue
            
            canon_url = f"{DOMAIN}{get_relative_url(lang_code, base)}"
            head.append(BeautifulSoup(f'<link rel="canonical" href="{canon_url}" />', 'lxml'))
            
            for sib_lang, sib_rel in langs.items():
                sib_url = f"{DOMAIN}{get_relative_url(sib_lang, base)}"
                hl = 'zh' if sib_lang == 'zh-CN' else sib_lang
                head.append(BeautifulSoup(f'<link rel="alternate" hreflang="{hl}" href="{sib_url}" />', 'lxml'))
                
            en_url = f"{DOMAIN}{get_relative_url('en', base)}"
            head.append(BeautifulSoup(f'<link rel="alternate" hreflang="x-default" href="{en_url}" />', 'lxml'))
            
            soup = inject_dynamic_lang_menu(soup, lang_code, base)
            
            with open(rel_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))

    today = datetime.now().strftime('%Y-%m-%d')
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    
    for base, langs in page_map.items():
        for lang_code, rel_path in langs.items():
            if '404.html' in rel_path or 'sitemap.html' in rel_path: continue
            url = f"{DOMAIN}{get_relative_url(lang_code, base)}".replace(' ', '%20')
            
            xml.append('  <url>')
            xml.append(f'    <loc>{url}</loc>')
            xml.append(f'    <lastmod>{today}</lastmod>')
            
            for sib_lang, sib_rel in langs.items():
                sib_url = f"{DOMAIN}{get_relative_url(sib_lang, base)}".replace(' ', '%20')
                hl = 'zh' if sib_lang == 'zh-CN' else sib_lang
                xml.append(f'    <xhtml:link rel="alternate" hreflang="{hl}" href="{sib_url}" />')
                
            en_url = f"{DOMAIN}{get_relative_url('en', base)}".replace(' ', '%20')
            xml.append(f'    <xhtml:link rel="alternate" hreflang="x-default" href="{en_url}" />')
            xml.append('  </url>')
            
    xml.append('</urlset>')
    with open('sitemap.xml', 'w', encoding='utf-8') as f:
        f.write('\n'.join(xml))
    print("✅ sitemap.xml generated perfectly.")

# ==========================================
# MAIN EXECUTION LOGIC
# ==========================================
def main():
    print("🚀 Starting Smart Incremental Translation Pipeline...")
    
    en_files = []
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in TARGET_LANGS and not d.startswith('.') and d not in ['scripts', 'node_modules', '.github']]
        for f in files:
            if f.endswith('.html'): en_files.append(os.path.join(root, f))
            
    modified_en_files = get_changed_english_files()
    print(f"📝 Detected {len(modified_en_files)} modified English files in latest push.")
    
    for en_path in en_files:
        rel_path = os.path.relpath(en_path, '.')
        needs_translation = rel_path in modified_en_files
        
        with open(en_path, 'r', encoding='utf-8') as f:
            en_soup = BeautifulSoup(f, 'lxml')
            
        for lang in TARGET_LANGS:
            trans_path = os.path.join(lang, rel_path)
            
            # ONLY translate if the file is missing OR if the English source was just updated
            if not os.path.exists(trans_path) or needs_translation:
                print(f"   🌍 Translating {rel_path} to {lang}...")
                lang_soup = BeautifulSoup(str(en_soup), 'lxml')
                lang_soup = extract_and_translate(lang_soup, lang)
                lang_soup.html['lang'] = 'zh' if lang == 'zh-CN' else lang
                lang_soup = fix_internal_links(lang_soup, lang)
                
                os.makedirs(os.path.dirname(trans_path), exist_ok=True)
                with open(trans_path, 'w', encoding='utf-8') as f:
                    f.write(str(lang_soup))

    inject_global_seo_and_sitemap()
    print("🎉 Pipeline Complete!")

if __name__ == "__main__":
    main()
