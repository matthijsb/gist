Applies LLM analysis on research papers for a given topic:


Create a (new) database to store all our results in:

    python create_db.py --db_name test.db


Scrape abstracts for a given query:

    python scrape.py --db_name test.db --query "NF1 AND (gist or men1 or cancer or neurofibromatosis)"

    * Note due to (cloudflare / scraping protection?) this will probably fail randomly, retry fetching failed articles afterwards:
    python scrape.py --db_name test.db --retry true


Now apply analysis on the abstracts to filter on relevant articles, we can try multiple promps for our "relevance" filter:

    python analyse.py --db_name test.db --key "YOUR_KEY_HERE" --prompt prompt-gist1.txt
    * This process can/should be run multiple times, with different prompts


Now we can generate a list of result that might show promise:

    python results.py --db_name test.db ?????????
