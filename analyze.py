import io
import os
import time
import json
import requests
import traceback
import argparse
import sqlite3

from typing import Dict
import urllib.parse
from urllib.request import pathname2url

import openai
from openai import OpenAI

#https://twitter.com/james_y_zou/status/1709608909395357946
#https://github.com/Weixin-Liang/LLM-scientific-feedback/tree/main
#https://www.reddit.com/r/Physics/comments/16deejy/update_about_my_project_gpt_powered_search_engine/?share_id=4e--HKM3QkRUfauQWBELv&utm_content=1&utm_medium=android_app&utm_name=androidcss&utm_source=share&utm_term=10
#https://platform.openai.com/docs/models/overview
#https://www.researchgate.net/


ap = argparse.ArgumentParser()
ap.add_argument("--db_name", required=True, help="the db file")
ap.add_argument("--key", required=True, help="your openai api key")
ap.add_argument("--prompt", required=True, help="the file decribing chatgpt's prompt")

params = vars(ap.parse_args())

dburi = 'file:{}?mode=rw'.format(pathname2url(params["db_name"]))
connection = sqlite3.connect(dburi, uri=True)
cursor = connection.cursor()


class GPTWrapper:
    def __init__(self, model_name):
        self.model_name = model_name
        self.client = OpenAI(
            # This is the default and can be omitted
            api_key=params["key"]
        )

    def send_query(self, user_str):
        return self.client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": user_str,
                }
            ],
            model=self.model_name,
        )


wrapper = GPTWrapper(model_name="gpt-4-turbo-2024-04-09") #"gpt-4-turbo")

task_def = open(params["prompt"]).read().strip()


articles = cursor.execute(f"SELECT id, abstract FROM papers WHERE status = 1").fetchall()
print(f"Analyzing {len(articles)} abstracts")
for article in articles:
    article_id = article[0]
    abstract = article[1]
    query_to_send = task_def.format(abstract=abstract, json_format='{"score": your probability score, "reason": your reason why}')
    review_generated = wrapper.send_query(query_to_send)
    raw = review_generated.dict()["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(raw)
        reason = parsed["reason"]
        score = float(parsed["score"])
        cursor.execute(f"INSERT INTO review(paper_id, raw, reason, score) VALUES (?, ?, ?, ?)", (article_id, raw, reason, score))
        cursor.execute(f"UPDATE papers SET status = 2 WHERE id = ?", (article_id,))
        cursor.execute(f"COMMIT")
        print("Succesfully analyzed article", article_id)
    except:
        print(traceback.format_exc())
        if raw:
            print("GPT RAW response: ", raw)

        print("Error analyzing article", article_id)
        cursor.execute(f"INSERT INTO review(paper_id, raw) VALUES (?, ?)", (article_id, raw,))
        cursor.execute(f"COMMIT")
