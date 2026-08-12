import os
import glob
from bs4 import BeautifulSoup

def cleanup_amp():
    print("🧹 Starting AMP Cleanup...")
    
    # 1. Delete all .amp and .amp.html files
    amp_patterns = ['**/*.amp', '**/*.amp.html']
    deleted_count = 0
    for pattern in amp_patterns:
        for f in glob.glob(pattern, recursive=True):
            try:
                os.remove(f)
                print(f"🗑️ Deleted: {f}")
                deleted_count += 1
            except Exception as e:
                print(f"⚠️ Could not delete {f}: {e}")
                
    # 2. Remove <link rel="amphtml"> from all HTML files
    html_files = glob.glob('**/*.html', recursive=True)
    cleaned_count = 0
    for f in html_files:
        try:
            with open(f, 'r', encoding='utf-8') as file:
                content = file.read()
                
            # Skip files that don't contain the tag to save time
            if 'amphtml' not in content:
                continue
                
            soup = BeautifulSoup(content, 'lxml')
            amp_links = soup.find_all('link', rel='amphtml')
            if amp_links:
                for link in amp_links:
                    link.decompose()
                with open(f, 'w', encoding='utf-8') as file:
                    file.write(str(soup))
                cleaned_count += 1
        except Exception as e:
            print(f"⚠️ Error processing {f}: {e}")
            
    print(f"🧼 Removed amphtml tags from {cleaned_count} files.")
    print("✅ AMP Cleanup Complete! (Your custom _redirects file was preserved).")

if __name__ == "__main__":
    cleanup_amp()
