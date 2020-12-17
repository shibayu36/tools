/* eslint-disable @typescript-eslint/no-non-null-assertion */
import axios from "axios";
import { parse } from "date-fns";
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
  date: Date;
  bookmark: number;
};
async function fetchArticles(browser: puppeteer.Browser, url: string): Promise<readonly ArticleWithBookmark[]> {
  const page = await browser.newPage();
  await page.goto(url);
  const articles = await page.evaluate(() => {
    const articleElements = Array.from(document.querySelectorAll(".archive-entry"));
    return articleElements.map((elem) => {
      const link = elem.querySelector(".entry-title-link")!;
      const title = link.textContent!;
      const url = link.getAttribute("href")!;
      const date = elem.querySelector(".archive-date time")!.getAttribute("datetime")!;
      return {
        title,
        url,
        date,
      };
    });
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
    title: a.title,
    url: a.url,
    date: parse(a.date, "yyyy-MM-dd", new Date()),
    bookmark: res.data[a.url] ?? 0,
  }));
}

main().catch((error) => console.error(error));
