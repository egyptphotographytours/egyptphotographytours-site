  // 🌍 Meta language
  if ($('meta[name="language"]').length) {
    $('meta[name="language"]').attr('content', lang);
  }

  // 📱 Open Graph locale
  if ($('meta[property="og:locale"]').length) {

    const locale =
      lang === 'en'
        ? 'en_US'
        : `${lang}_${lang.toUpperCase()}`;

    $('meta[property="og:locale"]').attr('content', locale);
  }

  // 🌐 Language switcher active state
  $('.lang-item').removeClass('is-active');

  const targetHref =
    lang === 'en'
      ? `/${fileName}`
      : `/${lang}/${fileName}`;

  $(`.lang-item[href="${targetHref}"]`)
    .addClass('is-active');
}

// 🚀 Main
async function main() {

  if (!filesToTranslate.length) {
    console.log('ℹ️ No HTML files found.');
    return;
  }

  console.log(`📄 Files: ${filesToTranslate.join(', ')}`);

  for (const file of filesToTranslate) {

    console.log(`\n🌐 Processing ${file}`);

    const html = fs.readFileSync(file, 'utf8');

    for (const lang of TARGET_LANGS) {

      process.stdout.write(` → ${lang} `);

      try {

        const clone$ = cheerio.load(html, {
          decodeEntities: false
        });

        await processHtml(clone$, lang, file);

        // Create folder
        const outDir = path.join('.', lang);

        if (!fs.existsSync(outDir)) {
          fs.mkdirSync(outDir, { recursive: true });
        }

        // Save translated page
        fs.writeFileSync(
          path.join(outDir, file),
          clone$.html(),
          'utf8'
        );

        process.stdout.write('✅\n');

      } catch (err) {

        process.stdout.write('❌\n');
        console.error(err.message);
      }
    }
  }

  console.log('\n🎉 Translation complete.');
}

// ❌ Fatal handling
main().catch(err => {
  console.error('\n❌ Fatal Error:\n', err);
  process.exit(1);
});
```

---
