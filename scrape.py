import json
import traceback
import sqlite3
import playwright
import requests
import argparse

import urllib.parse
from urllib.request import pathname2url

from parsel import Selector
from playwright.sync_api import sync_playwright
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

#https://serpapi.com/blog/web-scraping-all-researchgate-publications-in-python/


ap = argparse.ArgumentParser()
ap.add_argument("--db_name", required=True, help="the db file")
ap.add_argument("--query", required=False, help="the query to look for")
ap.add_argument("--page", type=int, required=False, default=1, help="the page nr to scrap from")
ap.add_argument("--pages", type=int, required=False, default=100, help="the nr of pages to scrape")
ap.add_argument("--retry", type=bool, required=False, default=False, help="Retry scraping failed articles")

params = vars(ap.parse_args())

dburi = 'file:{}?mode=rw'.format(pathname2url(params["db_name"]))
connection = sqlite3.connect(dburi, uri=True)
cursor = connection.cursor()


def scrape_researchgate_publications():
    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True, slow_mo=50)
        query_prompt = params['query']
        if not query_prompt:
            raise Exception("query is required when scraping")

        query_id = cursor.execute("SELECT id FROM query WHERE prompt = ?", (query_prompt,)).fetchone() #[0] or None
        if not query_id:
            safe_prompt = urllib.parse.quote_plus(query_prompt)
            cursor.execute(
                 f"INSERT INTO query(prompt, url, article_count, match_count) VALUES (?, ?, 0, 0) RETURNING id",
                (query_prompt, f"https://www.researchgate.net/search/publication?q={safe_prompt}")
            )
            # #Note: we cant return uuid from the insert, since it is created in a post inser trigger :S
            query_id = cursor.lastrowid
            # uuid = cursor.execute(f"SELECT uuid FROM query_prompt WHERE id = {cursor.lastrowid}").fetchone()[0]
            cursor.execute(f"COMMIT")
        else:
            query_id = query_id[0]

        page_nr = params["page"]
        article_nr = 0

        while True:

            page_url = f"https://www.researchgate.net/search/publication?q={query_prompt}&page={page_nr}"
            page_list = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36")
            page_list.goto(page_url)
            try:
                page_list.wait_for_selector(".nova-legacy-e-text")
                #except (PlaywrightTimeoutError, playwright._impl._errors.TimeoutError):
            except:
                print(traceback.format_exc())
                print("ERROR PAGE: ", page_url)
                cursor.execute(f"INSERT INTO failed_pages(query_id, url) VALUES (?, ?)", (query_id, page_url))
                cursor.execute(f"COMMIT")
                continue

            # https://stackoverflow.com/a/78137297
            publications = page_list.locator(".nova-legacy-e-text a").evaluate_all("els => els.map(el => el.href)")

            nr_pages = params["pages"]

            for idx, article_url in enumerate(publications):

                article_url = article_url.strip()
                article_url = article_url[0:article_url.rfind('?')]

                scrape_count = cursor.execute("SELECT COUNT(*) FROM papers WHERE url = ?", (article_url,)).fetchone()[0] or 0
                if scrape_count > 0:
                    print("SKIPPING DUPLICATE PAPER: ", article_url)
                    continue

                page_detail = browser.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36")
                page_detail.goto(article_url)
                try:
                    page_detail.wait_for_selector('.research-detail-header-section__title')
                except Exception:
                    print(traceback.format_exc())
                    print("ERROR ARTICLE: ", article_url)
                    if (cursor.execute("SELECT COUNT(*) FROM papers WHERE url = ?",
                                       (article_url,)).fetchone()[0] or 0) == 0:
                        cursor.execute(
                            f"INSERT INTO papers(query_id, url, title, abstract, page_nr, article_nr, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (query_id, article_url, None, None, page_nr, article_nr, -1))
                        cursor.execute(f"COMMIT")

                    page_detail.close()
                    continue

                html = page_detail.content()
                pub_selector = Selector(text=html)
                title = pub_selector.css('.research-detail-header-section__title::text').get()
                abstract = pub_selector.css('.research-detail-middle-section__abstract::text').get()
                article_nr += 1
                cursor.execute(f"INSERT INTO papers(query_id, url, title, abstract, page_nr, article_nr) VALUES (?, ?, ?, ?, ?, ?)",(query_id, article_url, title, abstract, page_nr, article_nr))
                cursor.execute(f"COMMIT")

                page_detail.close()
                print(f"NEXT ARTICLE: {idx + 1}: {article_url}")

            if page_nr == nr_pages: # or page_selector.css(".nova-legacy-c-button-group__item:nth-child(9) a::attr(rel)").get():
                print(f"Finished pagination at {page_nr} of {nr_pages}")
                break
            else:
                page_nr += 1
                print(f"Next page: {page_nr}")

            page_list.close()

        browser.close()


def retry_scraping():
    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True, slow_mo=50)

        articles = cursor.execute(f"SELECT id, url FROM papers WHERE status = -1").fetchall()
        retcount = len(articles)
        idx = 0
        while retcount > 0:

            article = articles[idx]
            article_id = article[0]
            publication_url = article[1]

            page_detail = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36")
            page_detail.goto(publication_url)
            try:
                page_detail.wait_for_selector('.research-detail-header-section__title')
            except (PlaywrightTimeoutError, playwright._impl._errors.TimeoutError):
                print("TIMEOUT ARTICLE: ", publication_url)
                continue

            html = page_detail.content()
            pub_selector = Selector(text=html)
            title = pub_selector.css('.research-detail-header-section__title::text').get()
            abstract = pub_selector.css('.research-detail-middle-section__abstract::text').get()

            cursor.execute(f"UPDATE papers SET title = ?, abstract = ?, status = 1 WHERE id = ?", (title, abstract, article_id))
            cursor.execute(f"COMMIT")

            retcount -= 1
            del articles[idx]
            if len(articles) == 0: break
            idx = (idx + 1) % len(articles)

            page_detail.close()

            print(f"FETCHED ARTICLE: {publication_url}")

        print("Finished scraping failed articles")
        browser.close()


if params["retry"]:
    retry_scraping()
else:
    scrape_researchgate_publications()
