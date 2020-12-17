import axios from "axios";
import puppeteer from "puppeteer";

async function main(): Promise<void> {
  const browser = await puppeteer.launch();
  const articles = await fetchArticles(browser, "https://blog.shibayu36.org/archive/category/tech");
  console.log(articles);

  await browser.close();
}

type ArticleWithBookmark = {
  title: string;
  url: string;
  bookmark: number;
};
async function fetchArticles(browser: puppeteer.Browser, url: string): Promise<readonly ArticleWithBookmark[]> {
  const page = await browser.newPage();
  await page.goto(url);
  const articles = await page.evaluate(() => {
    const links = Array.from(document.querySelectorAll(".entry-title-link"));
    return links.map((l) => ({
      title: l.textContent ?? "",
      url: l.getAttribute("href") ?? "",
    }));
  });
  page.close();

  const queries = new URLSearchParams();
  for (const article of articles) {
    queries.append("url", article.url);
  }
  const res = await axios.get<{ [url: string]: number }>(
    `https://bookmark.hatenaapis.com/count/entries?${queries.toString()}`
  );

  return articles.map((a) => ({
    ...a,
    bookmark: res.data[a.url] ?? 0,
  }));
}

main().catch((error) => console.error(error));
