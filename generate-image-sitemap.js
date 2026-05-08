const fs = require('fs');
const path = require('path');
const glob = require('glob');

const DOMAIN = 'https://www.egyptphotographytours.com';
const OUTPUT_FILE = './image-sitemap.xml';
const EXCLUDED = ['favicon', 'icon', 'apple-touch', 'android-chrome', 'mstile', 'browserconfig', 'logo', 'thumb'];

// 1️⃣ Auto-scan HTML files to find which page uses which image
function scanHTMLForImages() {
  const htmlFiles = glob.sync('**/*.html', { ignore: ['node_modules/**', '.github/**', '404.html'] });
  const imageMap = {};

  htmlFiles.forEach(file => {
    const html = fs.readFileSync(file, 'utf8');
    const matches = html.match(/<img[^>]+src=["']([^"']+)["']/gi) || [];
    
    matches.forEach(match => {
      const srcMatch = match.match(/src=["']([^"']+)["']/i);
      if (!srcMatch) return;
      
      const src = srcMatch[1].split('?')[0];
      const filename = path.basename(src);
      
      if (!/\.(jpg|jpeg|png|webp|gif)$/i.test(filename)) return;
      
      // Convert HTML file path to clean URL
      let url = '/' + file;
      if (url === '/index.html') url = '/';
      else if (url.endsWith('.html')) url = url.replace('.html', '');
      
      if (!imageMap[filename]) imageMap[filename] = [];
      if (!imageMap[filename].includes(url)) imageMap[filename].push(url);
    });
  });
  return imageMap;
}

// 2️⃣ Get all actual image files in /images/
function getAllImages() {
  return glob.sync('images/**/*.{jpg,jpeg,png,webp,gif}', { ignore: ['node_modules/**'] })
    .map(p => ({ path: p, filename: path.basename(p) }))
    .filter(img => !EXCLUDED.some(ex => img.filename.toLowerCase().includes(ex)));
}

// 3️⃣ Generate SEO-friendly metadata
function getMeta(filename) {
  const name = filename.replace(/\.[^/.]+$/, '').replace(/-/g, ' ');
  return {
    title: name.charAt(0).toUpperCase() + name.slice(1) + ' | Egypt Photography Tours',
    caption: 'Professional photography experience showcasing luxury private tours in Egypt'
  };
}

function escapeXml(str) {
  return str.replace(/[<>&'"]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;',"'":'&apos;','"':'&quot;'}[c] || c));
}

// 4️⃣ Build XML Sitemap
function generate() {
  const htmlMap = scanHTMLForImages();
  const images = getAllImages();
  const pageImages = {};

  images.forEach(({ path: imgPath, filename }) => {
    // Auto-map to HTML pages, fallback to homepage if not found in HTML
    const pages = htmlMap[filename] || ['/'];
    pages.forEach(page => {
      if (!pageImages[page]) pageImages[page] = [];
      pageImages[page].push({ path: imgPath, filename });
    });
  });

  let xml = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n`;

  Object.entries(pageImages).forEach(([page, imgs]) => {
    xml += `  <url>\n    <loc>${DOMAIN}${page}</loc>\n`;
    imgs.forEach(({ path, filename }) => {
      const meta = getMeta(filename);
      xml += `    <image:image>\n`;
      xml += `      <image:loc>${DOMAIN}/${path}</image:loc>\n`;
      xml += `      <image:title>${escapeXml(meta.title)}</image:title>\n`;
      xml += `      <image:caption>${escapeXml(meta.caption)}</image:caption>\n`;
      xml += `    </image:image>\n`;
    });
    xml += `  </url>\n`;
  });

  xml += `</urlset>`;
  fs.writeFileSync(OUTPUT_FILE, xml);
  console.log(`✅ Sitemap updated: ${Object.values(pageImages).flat().length} images across ${Object.keys(pageImages).length} pages`);
}

generate();
