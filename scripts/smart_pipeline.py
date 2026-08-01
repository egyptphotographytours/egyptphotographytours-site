import os
import re
import time
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

def get_url(lang_code, base_path):
    if lang_code == 'en':
        if base_path == 'index.html': return f"{DOMAIN}/"
        return f"{DOMAIN}/{base_path.replace('index.html', '')}"
    else:
        if base_path == 'index.html': return f"{DOMAIN}/{lang_code}/"
        return f"{DOMAIN}/{lang_code}/{base_path.replace('index.html', '')}"

def get_relative_url(lang_code, base_path):
    if lang_code == 'en':
        if base_path == 'index.html': return "/"
        return f"/{base_path.replace('index.html', '')}"
    else:
        if base_path == 'index.html': return f"/{lang_code}/"
        return f"/{lang_code}/{base_path.replace('index.html', '')}"

# ==========================================
# 1. FIX INTERNAL LINKS & LANGUAGE SWITCHER
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
            a['href'] = f"/{target_lang}/{href}"
    return soup

def inject_dynamic_lang_menu(soup, target_lang, rel_path):
    lang_menu = soup.find('div', id='lang-menu')
    if not lang_menu: return soup

    for old_link in lang_menu.find_all('a', class_='lang-item'):
        old_link.decompose()

    base_path = rel_path
    for lang in TARGET_LANGS:
        if base_path.startswith(f"{lang}/"):
            base_path = base_path[len(f"{lang}/"):]
            break

    # Add English
    en_url = get_relative_url('en', base_path)
    is_active = "is-active" if target_lang == 'en' else ""
    en_html = f'<a href="{en_url}" class="lang-item {is_active}" role="menuitem"><span class="lang-flag" aria-hidden="true">🇺🇸</span><span class="lang-name">English</span></a>'
    lang_menu.append(BeautifulSoup(en_html, 'lxml'))

    # Add other languages ONLY IF they exist
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
# 2. PATCH EXISTING BROKEN FILES
# ==========================================
def patch_existing_translated_file(translated_path, en_soup, target_lang, base_rel_path):
    print(f"   🔧 Patching {translated_path}...")
    with open(translated_path, 'r', encoding='utf-8') as f:
        trans_soup = BeautifulSoup(f, 'lxml')

    for tag in trans_soup.find_all(['script', 'style']):
        tag.decompose()
        
    head = trans_soup.find('head')
    body = trans_soup.find('body')
    
    for tag in en_soup.find_all(['script', 'style']):
        new_tag = BeautifulSoup(str(tag), 'lxml')
        if head and tag.find_parent('head'): head.append(new_tag)
        elif body: body.append(new_tag)
        elif head: head.append(new_tag)

    trans_soup.html['lang'] = 'zh' if target_lang == 'zh-CN' else target_lang
    trans_soup = fix_internal_links(trans_soup, target_lang)
    trans_soup = inject_dynamic_lang_menu(trans_soup, target_lang, translated_path)

    with open(translated_path, 'w', encoding='utf-8') as f:
        f.write(str(trans_soup))

# ==========================================
# 3. TRANSLATE MISSING FILES
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

def translate_missing_file(en_path, en_soup, target_lang, out_path):
    print(f"   🌍 Translating missing file to {target_lang}: {out_path}")
    lang_soup = BeautifulSoup(str(en_soup), 'lxml')
    
    texts, nodes = [], []
    if lang_soup.title and lang_soup.title.string:
        texts.append(lang_soup.title.string.strip())
        nodes.append(('title', lang_soup.title))
        
    for meta_name in ['description', 'og:title', 'og:description', 'twitter:title', 'twitter:description']:
        tag = lang_soup.find('meta', attrs={'name': meta_name}) or lang_soup.find('meta', attrs={'property': meta_name})
        if tag and tag.get('content'):
            texts.append(tag['content'].strip())
            nodes.append(('meta', tag))
            
    for img in lang_soup.find_all('img', alt=True):
        if img['alt'].strip() and not img['alt'].startswith('http'):
            texts.append(img['alt'].strip())
            nodes.append(('alt', img))
            
    for text_node in lang_soup.find_all(string=True):
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

    lang_soup.html['lang'] = 'zh' if target_lang == 'zh-CN' else target_lang
    lang_soup = fix_internal_links(lang_soup, target_lang)
    
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(str(lang_soup))

# ==========================================
# 4. GLOBAL SEO INJECTION & SITEMAP
# ==========================================
def inject_global_seo_and_sitemap():
    print("🔗 Injecting Global SEO Tags & Generating Sitemap...")
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
            
            canon_url = get_url(lang_code, base)
            head.append(BeautifulSoup(f'<link rel="canonical" href="{canon_url}" />', 'lxml'))
            
            for sib_lang, sib_rel in langs.items():
                sib_url = get_url(sib_lang, base)
                hl = 'zh' if sib_lang == 'zh-CN' else sib_lang
                head.append(BeautifulSoup(f'<link rel="alternate" hreflang="{hl}" href="{sib_url}" />', 'lxml'))
                
            en_url = get_url('en', base)
            head.append(BeautifulSoup(f'<link rel="alternate" hreflang="x-default" href="{en_url}" />', 'lxml'))
            
            # Rebuild Language Menu for all files to ensure perfect switching
            soup = inject_dynamic_lang_menu(soup, lang_code, rel_path)
            
            with open(rel_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))

    today = datetime.now().strftime('%Y-%m-%d')
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    
    for base, langs in page_map.items():
        for lang_code, rel_path in langs.items():
            if '404.html' in rel_path or 'sitemap.html' in rel_path: continue
            url = get_url(lang_code, base).replace(' ', '%20')
            
            xml.append('  <url>')
            xml.append(f'    <loc>{url}</loc>')
            xml.append(f'    <lastmod>{today}</lastmod>')
            
            for sib_lang, sib_rel in langs.items():
                sib_url = get_url(sib_lang, base).replace(' ', '%20')
                hl = 'zh' if sib_lang == 'zh-CN' else sib_lang
                xml.append(f'    <xhtml:link rel="alternate" hreflang="{hl}" href="{sib_url}" />')
                
            en_url = get_url('en', base).replace(' ', '%20')
            xml.append(f'    <xhtml:link rel="alternate" hreflang="x-default" href="{en_url}" />')
            xml.append('  </url>')
            
    xml.append('</urlset>')
    with open('sitemap.xml', 'w', encoding='utf-8') as f:
        f.write('\n'.join(xml))
    print("✅ sitemap.xml generated perfectly.")

def main():
    print("🚀 Starting Smart Patch & Translation Pipeline...")
    en_files = []
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in TARGET_LANGS and not d.startswith('.') and d not in ['scripts', 'node_modules', '.github']]
        for f in files:
            if f.endswith('.html'): en_files.append(os.path.join(root, f))
            
    for en_path in en_files:
        rel_path = os.path.relpath(en_path, '.')
        print(f"📄 Processing English Source: {rel_path}")
        
        with open(en_path, 'r', encoding='utf-8') as f:
            en_soup = BeautifulSoup(f, 'lxml')
            
        for lang in TARGET_LANGS:
            trans_path = os.path.join(lang, rel_path)
            
            if os.path.exists(trans_path):
                patch_existing_translated_file(trans_path, en_soup, lang, rel_path)
            else:
                translate_missing_file(en_path, en_soup, lang, trans_path)

    inject_global_seo_and_sitemap()
    print("🎉 Pipeline Complete!")

if __name__ == "__main__":
    main()
