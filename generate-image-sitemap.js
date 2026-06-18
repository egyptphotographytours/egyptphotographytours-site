import fs from 'fs';
import path from 'path';
import { globSync } from 'glob';

const DOMAIN = 'https://www.egyptphotographytours.com';
const OUTPUT_FILE = './image-sitemap.xml';

const EXCLUDED = [
  'favicon',
  'icon',
  'apple-touch',
  'android-chrome',
  'mstile',
  'browserconfig',
  'logo',
  'thumb'
];

// ===============================
// Escape XML special characters
// ===============================
function escapeXml(str) {
  return str.replace(/[<>&'"]/g, c => ({
    '<': '&lt;',
    '>': '&gt;',
    '&': '&amp;',
    "'": '&apos;',
    '"': '&quot;'
  }[c]));
}


// ===============================
// Convert HTML path → clean URL
// ===============================
function normalizePageUrl(file) {

  let url = '/' + file.replace(/\\/g, '/');

  if (url === '/index.html') {
    return '/';
  }

  if (url.endsWith('/index.html')) {
    return url.replace('/index.html', '') || '/';
  }

  if (url.endsWith('.html')) {
    return url.replace('.html', '');
  }

  return url;
}


// ===============================
// Image SEO metadata
// ===============================
function getMeta(filename) {

  const cleanName = filename
    .replace(/\.[^/.]+$/, '')
    .replace(/[-_]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();


  const formatted =
    cleanName.charAt(0).toUpperCase() + cleanName.slice(1);


  return {

    title:
      `${formatted} | Egypt Photography Tours`,

    caption:
      'Private Egypt photography tours with professional photoshoots in Cairo, Giza, Alexandria and across Egypt'

  };
}


// ===============================
// Scan HTML references
// ===============================
function scanHTMLForImages() {

  const htmlFiles = globSync('**/*.html', {
    ignore: [
      'node_modules/**',
      '.github/**',
      '404.html'
    ]
  });


  const imageMap = {};


  htmlFiles.forEach(file => {


    const html = fs.readFileSync(file, 'utf8');


    const matches =
      html.match(/<img[^>]+src=["']([^"']+)["']/gi) || [];


    const pageUrl = normalizePageUrl(file);



    matches.forEach(match => {


      const srcMatch =
        match.match(/src=["']([^"']+)["']/i);


      if (!srcMatch) return;


      let src =
        srcMatch[1]
        .split('?')[0];


      if (
        src.startsWith('http') ||
        src.startsWith('//')
      ) {
        return;
      }


      src =
        src
        .replace(/^\.?\//, '')
        .replace(/\\/g, '/');



      if (!/\.(jpg|jpeg|png|webp|gif)$/i.test(src)) {
        return;
      }



      if (!imageMap[src]) {
        imageMap[src] = [];
      }


      if (!imageMap[src].includes(pageUrl)) {
        imageMap[src].push(pageUrl);
      }


    });


  });


  return imageMap;

}


// ===============================
// Get ALL images from images folder
// ===============================
function getAllImages() {


  return globSync(
    'images/**/*.{jpg,jpeg,png,webp,gif}',
    {
      ignore: ['node_modules/**']
    }
  )

  .map(imgPath => ({

    path:
      imgPath.replace(/\\/g, '/'),

    filename:
      path.basename(imgPath)

  }))


  .filter(img =>

    !EXCLUDED.some(ex =>

      img.filename
      .toLowerCase()
      .includes(ex)

    )

  );


}


// ===============================
// Generate sitemap
// ===============================
function generate() {


  const imageMap =
    scanHTMLForImages();


  const images =
    getAllImages();



  const today =
    new Date()
    .toISOString()
    .split('T')[0];



  let xml =
`<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
`;



  let totalUrls = 0;
  let totalImages = 0;



  images.forEach(({path: imgPath, filename}) => {



    // use HTML page if found
    // otherwise use homepage

    const pages =
      imageMap[imgPath] || ['/'];



    const meta =
      getMeta(filename);



    pages.forEach(page => {



      xml += `
<url>
  <loc>${DOMAIN}${page}</loc>
  <lastmod>${today}</lastmod>

  <image:image>

    <image:loc>
      ${DOMAIN}/${imgPath}
    </image:loc>

    <image:title>
      ${escapeXml(meta.title)}
    </image:title>

    <image:caption>
      ${escapeXml(meta.caption)}
    </image:caption>

  </image:image>

</url>
`;



      totalUrls++;
      totalImages++;


    });



  });



  xml += `
</urlset>`;



  fs.writeFileSync(
    OUTPUT_FILE,
    xml
  );



  console.log(
    '✅ Image sitemap generated successfully'
  );

  console.log(
    `📄 URLs: ${totalUrls}`
  );

  console.log(
    `🖼️ Images: ${totalImages}`
  );


}



generate();
