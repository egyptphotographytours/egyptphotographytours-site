import fs from "fs";
import path from "path";
import * as cheerio from "cheerio";
import crypto from "crypto";

// 🌍 LANGUAGES
const LANGS = [
  "ar","fr","de","es","it","zh","ko","pt","ru","ja",
  "nl","hi","sv","no","da","fi","th","ms","tl","id"
];

// 🌐 SITE
const BASE_URL = "https://www.egyptphotographytours.com";

// 💾 CACHE (prevents re-translation)
const CACHE_FILE = "./translation-cache.json";

let cache = fs.existsSync(CACHE_FILE)
  ? JSON.parse(fs.readFileSync(CACHE_FILE, "utf8"))
  : {};

// ---------------- HASH ----------------
const hash = (str) =>
  crypto.createHash("md5").update(str).digest("hex");

// ---------------- TRANSLATE (STABLE API) ----------------
async function translate(text, lang) {
  const key = `${lang}:${text}`;
  const h = hash(key);

  if (cache[h]) return cache[h];

  try {
    const url = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=${lang}&dt=t&q=${encodeURIComponent(text)}`;

    const res = await fetch(url);
    const data = await res.json();

    const translated =
      data?.[0]?.map(x => x[0]).join("") || text;

    cache[h] = translated;
    return translated;

  } catch (e) {
    console.log("Translate error:", e.message);
    return text;
  }
}

// ---------------- TEXT EXTRACTION ----------------
function extractTexts($) {
  const texts = new Set();

  $("body *").each((_, el) => {
    const t = $(el).text().trim();

    if (!t) return;
    if (t.length < 3 || t.length > 200) return;

    texts.add(t);
  });

  return [...texts];
}

// ---------------- SEO UPDATE ----------------
function updateSEO($, lang, fileName) {

  const pageUrl =
    lang === "en"
      ? `${BASE_URL}/${fileName}`
      : `${BASE_URL}/${lang}/${fileName}`;

  // HTML language
  $("html").attr("lang", lang);

  // RTL support
  $("html").attr(
    "dir",
    ["ar","he","fa","ur"].includes(lang) ? "rtl" : "ltr"
  );

  // Canonical
  $("link[rel='canonical']").remove();
  $("head").append(`<link rel="canonical" href="${pageUrl}" />`);

  // hreflang cleanup
  $("link[rel='alternate'][hreflang]").remove();

  const langs = ["en", ...LANGS];

  for (const l of langs) {
    const href =
      l === "en"
        ? `${BASE_URL}/${fileName}`
        : `${BASE_URL}/${l}/${fileName}`;

    $("head").append(
      `<link rel="alternate" hreflang="${l}" href="${href}">`
    );
  }

  $("head").append(
    `<link rel="alternate" hreflang="x-default" href="${BASE_URL}/${fileName}">`
  );
}

// ---------------- LANGUAGE SWITCHER ----------------
function updateLangSwitcher($, lang, fileName) {
  $(".lang-item").removeClass("active");

  const target =
    lang === "en"
      ? `/${fileName}`
      : `/${lang}/${fileName}`;

  $(`.lang-item[href='${target}']`).addClass("active");
}

// ---------------- PROCESS FILE ----------------
async function processFile(file, lang) {

  const html = fs.readFileSync(file, "utf8");
  const $ = cheerio.load(html);

  const texts = extractTexts($);

  const translated = [];

  for (const t of texts) {
    translated.push(await translate(t, lang));
  }

  $("body *").each((_, el) => {
    const node = $(el);
    const t = node.text().trim();

    const index = texts.indexOf(t);
    if (index !== -1) {
      node.text(translated[index]);
    }
  });

  updateSEO($, lang, file);
  updateLangSwitcher($, lang, file);

  return $.html();
}

// ---------------- MAIN ----------------
async function main() {

  const files = fs
    .readdirSync(".")
    .filter(f => f.endsWith(".html"));

  for (const file of files) {

    console.log(`📄 Processing: ${file}`);

    for (const lang of LANGS) {

      const outDir = path.join(".", lang);
      if (!fs.existsSync(outDir)) {
        fs.mkdirSync(outDir);
      }

      const result = await processFile(file, lang);

      fs.writeFileSync(
        path.join(outDir, file),
        result,
        "utf8"
      );

      console.log(`✅ ${lang}/${file}`);
    }
  }

  fs.writeFileSync(
    CACHE_FILE,
    JSON.stringify(cache, null, 2)
  );

  console.log("🎉 SEO PRO translation complete");
}

main().catch(err => {
  console.error("FATAL ERROR:", err);
  process.exit(1);
});
