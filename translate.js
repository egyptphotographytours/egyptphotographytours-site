import fs from "fs";
import path from "path";
import * as cheerio from "cheerio";
import crypto from "crypto";

const LANGS = [
  "ar","fr","de","es","it","zh","ko","pt","ru","ja",
  "nl","hi","sv","no","da","fi","th","ms","tl","id"
];

const API = "https://translate.terraprint.co/translate";
const CACHE_FILE = "./.translation-cache.json";

let cache = {};

if (fs.existsSync(CACHE_FILE)) {
  cache = JSON.parse(fs.readFileSync(CACHE_FILE, "utf8"));
}

function hash(text) {
  return crypto.createHash("md5").update(text).digest("hex");
}

async function translate(text, lang) {
  const key = `${lang}:${text}`;
  const h = hash(key);

  if (cache[h]) return cache[h];

  for (let i = 0; i < 2; i++) {
    try {
      const res = await fetch(API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          q: text,
          source: "en",
          target: lang,
          format: "text"
        })
      });

      const data = await res.json();
      const out = data.translatedText || text;

      cache[h] = out;
      return out;

    } catch (e) {
      console.log(`Retry ${i + 1} failed for ${lang}`);
    }
  }

  return text;
}

async function process(file) {
  const html = fs.readFileSync(file, "utf8");
  const $ = cheerio.load(html);

  const texts = $("body *").toArray();

  for (const el of texts) {
    const node = $(el);
    const t = node.text().trim();

    if (!t || t.length < 2 || t.length > 300) continue;

    const lang = node.attr("data-lang") || null;
    const translated = await translate(t, lang || "en");

    if (translated !== t) node.text(translated);
  }

  return $.html();
}

async function main() {
  const files = fs.readdirSync(".").filter(f => f.endsWith(".html"));

  for (const file of files) {
    const original = fs.readFileSync(file, "utf8");
    const originalHash = hash(original);

    for (const lang of LANGS) {
      const outDir = path.join(lang);
      if (!fs.existsSync(outDir)) fs.mkdirSync(outDir);

      const outFile = path.join(outDir, file);

      if (fs.existsSync(outFile)) {
        const existing = fs.readFileSync(outFile, "utf8");
        if (hash(existing) === originalHash) {
          console.log(`Skipping ${lang}/${file}`);
          continue;
        }
      }

      const translated = await process(file);
      fs.writeFileSync(outFile, translated);
      console.log(`Done ${lang}/${file}`);
    }
  }

  fs.writeFileSync(CACHE_FILE, JSON.stringify(cache, null, 2));
}

main().catch(err => {
  console.error("FATAL:", err);
  process.exit(1);
});
