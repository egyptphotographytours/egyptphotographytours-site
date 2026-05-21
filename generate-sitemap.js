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

  return url;
}

function generate() {
  const htmlFiles = glob.sync('**/*.html', {
    ignore: [
      'node_modules/**',
      '.github/**',
      '404.html'
    ]
  });

  const today = new Date().toISOString().split('T')[0];

  let xml = `<?xml version="1.0" encoding="UTF-8"?>\n`;
  xml += `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`;

  htmlFiles.forEach(file => {
    const url = normalizeUrl(file);

    xml += `  <url>\n`;
    xml += `    <loc>${DOMAIN}${url}</loc>\n`;
    xml += `    <lastmod>${today}</lastmod>\n`;
    xml += `    <changefreq>weekly</changefreq>\n`;
    xml += `    <priority>${url === '/' ? '1.0' : '0.8'}</priority>\n`;
    xml += `  </url>\n`;
  });

  xml += `</urlset>`;

  fs.writeFileSync(OUTPUT_FILE, xml);

  console.log('✅ sitemap.xml generated');
}

generate();
