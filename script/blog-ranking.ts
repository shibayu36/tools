/* eslint-disable @typescript-eslint/no-non-null-assertion */
import axios from "axios";
import { parse, parseISO, isBefore } from "date-fns";
import { sumBy, sortBy } from "lodash";
import puppeteer from "puppeteer";

const start = parseISO("2020-07-01T00:00:00+09:00");
const end = parseISO("2021-01-01T00:00:00+09:00");
const urls = [
  "https://blog.shibayu36.org/archive/category/tech",
  "https://blog.shibayu36.org/archive/category/tech?page=2",
];

async function main(): Promise<void> {
  const browser = await puppeteer.launch();
  const articlesList = await Promise.all(urls.map((u) => fetchArticles(browser, u)));
  const articles = articlesList.flat().filter((a) => isBefore(start, a.date) && isBefore(a.date, end));

  console.log("総記事数:", articles.length);
  console.log("総ブックマーク数:" + sumBy(articles, "bookmark"));
  for (const a of sortBy(articles, [(a) => -a.bookmark])) {
    console.log(`[${a.title} ${a.url}]`, a.bookmark);
  }

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
