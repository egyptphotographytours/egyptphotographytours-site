const fs = require('fs');
const glob = require('glob');

const DOMAIN = 'https://www.egyptphotographytours.com';
const OUTPUT_FILE = './sitemap.xml';

function normalizeUrl(file) {
  let url = '/' + file.replace(/\\/g, '/');

  if (url === '/index.html') {
    return '/';
  }

  if (url.endsWith('/index.html')) {
    url = url.replace('/index.html', '');
    return url || '/';
  }

  if (url.endsWith('.html')) {
    url = url.replace('.html', '');
  }

  // FIX 1: Encode spaces to %20 to prevent invalid XML/URL errors in Google Console
  url = url.replace(/ /g, '%20');

  return url;
}

function generate() {
  const htmlFiles = glob.sync('**/*.html', {
    ignore: [
      'node_modules/**',
      '.github/**',
      '404.html',
      'sitemap.html'
    ]
  });

  const today = new Date().toISOString().split('T')[0];

  let xml = `<?xml version="1.0" encoding="UTF-8"?>\n`;
  xml += `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`;

  htmlFiles.forEach(file => {
    const rawUrl = normalizeUrl(file);
    const fullUrl = `${DOMAIN}${rawUrl}`;

    // FIX 2: Skip any URLs that contain double-language paths (e.g., /fr/de/, /ar/en/)
    if (/\/[a-z]{2}\/[a-z]{2}\//i.test(rawUrl)) {
      console.log(`⚠️ Skipped invalid double-language path: ${fullUrl}`);
      return;
    }

    // Determine priority and changefreq based on page type
    let priority = '0.5';
    let changefreq = 'monthly';

    if (rawUrl === '/' || rawUrl === '/index') {
      priority = '1.0';
      changefreq = 'weekly';
    } else if (rawUrl.includes('/contact')) {
      priority = '0.8';
      changefreq = 'monthly';
    } else if (rawUrl.includes('/tours')) {
      priority = '0.9';
      changefreq = 'weekly';
    } else if (rawUrl.includes('/blog')) {
      priority = '0.6';
      changefreq = 'daily';
    }

    xml += `  <url>\n`;
    xml += `    <loc>${fullUrl}</loc>\n`;
    xml += `    <lastmod>${today}</lastmod>\n`;
    xml += `    <changefreq>${changefreq}</changefreq>\n`;
    xml += `    <priority>${priority}</priority>\n`;
    xml += `  </url>\n`;
  });

  xml += `</urlset>`;

  fs.writeFileSync(OUTPUT_FILE, xml);
  console.log('✅ sitemap.xml generated successfully with validations!');
}

generate();
