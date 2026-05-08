const fs = require('fs');
const path = require('path');
const glob = require('glob');

// Configuration
const DOMAIN = 'https://www.egyptphotographytours.com';
const IMAGES_DIR = './images';
const OUTPUT_FILE = './image-sitemap.xml';

// Map images to their respective pages
const IMAGE_TO_PAGE_MAP = {
  // Homepage images
  'hero-image1.jpg': '/',
  'hero-image2.jpg': '/',
  'hero-image3.jpg': '/',
  'hero-image4.jpg': '/',
  'hero-image5.jpg': '/',
  'egypt-photography-tours-hero-image.jpg': '/',
  
  // Tour page images
  'pyramids-private-tour.jpg': '/tour-pyramids-private',
  'cairo-giza-2day.jpg': '/tour-cairo-giza-2day',
  'alexandria-tour.jpg': '/tour-alexandria',
  'egypt-discovery-7day.jpg': '/tour-egypt-discovery-7day',
  
  // About page
  'hossam-photographer.jpg': '/about',
  
  // Logo (only if you want it indexed)
  // 'logo.jpg': '/',
};

// Images to exclude from sitemap (UI elements, icons, etc.)
const EXCLUDED_PATTERNS = [
  'favicon',
  'icon',
  'apple-touch',
  'android-chrome',
  'mstile',
  'browserconfig',
  'site.webmanifest'
];

// Image metadata templates
const IMAGE_METADATA = {
  'hero-image1.jpg': {
    title: 'Professional photographer capturing golden hour sunset at Pyramids of Giza',
    caption: 'Luxury private Egypt photography tour: Golden hour photoshoot at the Great Pyramid of Giza with professional photographer guide Hossam'
  },
  'hero-image2.jpg': {
    title: 'Golden hour pyramids photoshoot luxury private tour Egypt',
    caption: 'Magical sunset photography at the Giza Pyramids during private luxury photography experience'
  },
  'hero-image3.jpg': {
    title: 'Cairo street photography adventure with professional guide',
    caption: 'Explore vibrant Cairo markets and streets with expert photography guide'
  },
  'hero-image4.jpg': {
    title: '7-day Egypt photography journey luxury tour',
    caption: 'Complete luxury photography adventure from Cairo to Alexandria with daily photoshoots'
  },
  'hero-image5.jpg': {
    title: 'Exclusive 2026 Egypt photography experiences',
    caption: 'New personalized luxury photography tours and unforgettable moments in Egypt'
  },
  'egypt-photography-tours-hero-image.jpg': {
    title: 'Egypt Photography Tours - Luxury Private Photography Experiences',
    caption: 'Professional photographer capturing magical moments at Pyramids, Cairo streets and Alexandria coast for families, couples and solo travelers'
  },
  'pyramids-private-tour.jpg': {
    title: 'Private luxury pyramids photography tour Giza Egypt golden hour',
    caption: 'Romantic couples photography tour at Pyramids of Giza during golden hour - luxury private Egypt experience for families and content creators'
  },
  'cairo-giza-2day.jpg': {
    title: 'Cairo Giza 2 day luxury photography tour professional guide',
    caption: 'Family photography tour in Cairo and Giza: Professional photographer capturing memories at Egyptian landmarks with golden hour sessions'
  },
  'alexandria-tour.jpg': {
    title: 'Alexandria luxury photography day trip Mediterranean coast Egypt',
    caption: 'Luxury Alexandria coastal photography tour: Professional photographer guide at Mediterranean landmarks, Catacombs and Citadel with golden hour lighting'
  },
  'egypt-discovery-7day.jpg': {
    title: '7 day luxury Egypt photography adventure Cairo Luxor professional guide',
    caption: 'Multi-day luxury Egypt photography journey: Professional photographer capturing ancient temples and cultural moments in Cairo, Giza and Luxor with daily photoshoots'
  },
  'hossam-photographer.jpg': {
    title: 'Hossam - Professional Photographer and Egyptologist Guide',
    caption: 'Award-winning Egyptian professional photographer specializing in luxury private photography tours and golden hour Pyramids photoshoots since 2015'
  }
};

function shouldExclude(filename) {
  const lowerFilename = filename.toLowerCase();
  return EXCLUDED_PATTERNS.some(pattern => lowerFilename.includes(pattern));
}

function getImageMetadata(filename) {
  return IMAGE_METADATA[filename] || {
    title: filename.replace(/\.[^/.]+$/, '').replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) + ' - Egypt Photography Tour',
    caption: 'Professional photography experience at iconic Egyptian landmark'
  };
}

function escapeXml(unsafe) {
  return unsafe.replace(/[<>&'"]/g, c => {
    switch (c) {
      case '<': return '&lt;';
      case '>': return '&gt;';
      case '&': return '&amp;';
      case '\'': return '&apos;';
      case '"': return '&quot;';
    }
  });
}

function generateSitemap() {
  // Get all image files
  const imageFiles = glob.sync('**/*.{jpg,jpeg,png,webp,gif}', {
    cwd: IMAGES_DIR,
    ignore: ['**/node_modules/**', '**/.git/**']
  });

  // Filter out excluded files
  const validImages = imageFiles.filter(file => !shouldExclude(file));

  // Group images by page URL
  const pageImages = {};
  validImages.forEach(file => {
    const page = IMAGE_TO_PAGE_MAP[file] || '/';
    if (!pageImages[page]) {
      pageImages[page] = [];
    }
    pageImages[page].push(file);
  });

  // Generate XML
  let xml = `<?xml version="1.0" encoding="UTF-8"?>\n`;
  xml += `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n`;
  xml += `        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n`;

  Object.entries(pageImages).forEach(([pageUrl, images]) => {
    xml += `  <url>\n`;
    xml += `    <loc>${DOMAIN}${pageUrl}</loc>\n`;
    
    images.forEach(img => {
      const metadata = getImageMetadata(img);
      xml += `    <image:image>\n`;
      xml += `      <image:loc>${DOMAIN}/images/${img}</image:loc>\n`;
      xml += `      <image:title>${escapeXml(metadata.title)}</image:title>\n`;
      xml += `      <image:caption>${escapeXml(metadata.caption)}</image:caption>\n`;
      
      // Add license for commercial images
      if (img.includes('tour') || img.includes('hero')) {
        xml += `      <image:license>${DOMAIN}/image-license</image:license>\n`;
      }
      
      xml += `    </image:image>\n`;
    });

    xml += `  </url>\n`;
  });

  xml += `</urlset>`;

  // Write file
  fs.writeFileSync(OUTPUT_FILE, xml, 'utf8');
  
  console.log(`✅ Generated ${OUTPUT_FILE}`);
  console.log(`📊 Total images indexed: ${validImages.length}`);
  console.log(`📄 Total URLs with images: ${Object.keys(pageImages).length}`);
  
  // Log summary
  Object.entries(pageImages).forEach(([page, imgs]) => {
    console.log(`   ${page}: ${imgs.length} image(s)`);
  });
}

// Run the generator
try {
  generateSitemap();
} catch (error) {
  console.error('❌ Error generating sitemap:', error.message);
  process.exit(1);
}
