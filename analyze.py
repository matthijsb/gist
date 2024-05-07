import json
import traceback
import argparse
import sqlite3

from urllib.request import pathname2url

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
ap.add_argument("--fix", required=False, default=False, help="Try fixing most common GPT json output errors and extract results")

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


def fix():
    retry = cursor.execute("SELECT id, raw FROM llm_review WHERE raw IS NOT NULL and score IS NULL").fetchall()
    for x in retry:
        try:
            raw_fixed = x[1].replace('```json\n', '')
            raw_fixed = raw_fixed.replace('\n```', '')
            parsed = json.loads(raw_fixed)
            reason = parsed["reason"]
            score = float(parsed["score"])
            cursor.execute(f"UPDATE llm_review SET raw=?, reason=?, score=? WHERE id=?",(raw_fixed, reason, score, x[0]))
            cursor.execute(f"COMMIT")
        except:
            print(traceback.format_exc())

def run():
    wrapper = GPTWrapper(model_name="gpt-4-turbo-2024-04-09")  # "gpt-4-turbo")

    task_def = open(params["prompt"]).read().strip()

    prompt_id = cursor.execute("SELECT id FROM llm_prompt WHERE prompt = ?", (task_def,)).fetchone()  # [0] or None
    if not prompt_id:
        cursor.execute(f"INSERT INTO llm_prompt(prompt) VALUES (?) RETURNING id", (task_def,))
        prompt_id = cursor.lastrowid
        cursor.execute(f"COMMIT")
    else:
        prompt_id = prompt_id[0]

    articles = cursor.execute(f"SELECT id, abstract FROM papers WHERE status = 1").fetchall()
    print(f"Analyzing {len(articles)} abstracts")
    for article in articles:
        article_id = article[0]
        abstract = article[1]
        query_to_send = task_def.format(abstract=abstract,
                                        json_format='{"score": your probability score, "reason": your reason why}')
        review_generated = wrapper.send_query(query_to_send)
        raw = review_generated.dict()["choices"][0]["message"]["content"]
        try:
            parsed = json.loads(raw)
            reason = parsed["reason"]
            score = float(parsed["score"])
            cursor.execute(f"INSERT INTO llm_review(prompt_id, paper_id, raw, reason, score) VALUES (?, ?, ?, ?, ?)",
                           (prompt_id, article_id, raw, reason, score))
            cursor.execute(f"UPDATE papers SET status = 2 WHERE id = ?", (article_id,))
            cursor.execute(f"COMMIT")
            print("Succesfully analyzed article", article_id)
        except:
            print(traceback.format_exc())
            if raw:
                print("GPT RAW response: ", raw)

            print("Error analyzing article", article_id)
            cursor.execute(f"INSERT INTO llm_review(prompt_id, paper_id, raw) VALUES (?, ?, ?)",
                           (prompt_id, article_id, raw,))
            cursor.execute(f"COMMIT")


if params["fix"]:
    fix()
else:
    run()
