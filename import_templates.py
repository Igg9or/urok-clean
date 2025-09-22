import sqlite3
import json
import psycopg2
import psycopg2.extras
import glob

DB_PATH = 'mathdbnew'        # имя базы
DB_USER = 'mathuser'         # пользователь
DB_PASSWORD = '1501'         # пароль
DB_HOST = 'localhost'        # хост

# список файлов-шаблонов
JSON_FILES = [
    "templates5.json",
    "templates6.json",
    "templates7.json",
    "templates8.json",
    "templates9.json"
]

conn = psycopg2.connect(
    dbname=DB_PATH,
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST
)
cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) 

for file in JSON_FILES:
    print(f"📂 Загружаю {file}...")
    with open(file, encoding='utf-8') as f:
        content = f.read().strip()
        if not content:
            print(f"⚠️ Файл {file} пустой, пропускаю")
            continue
        try:
            templates = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"❌ Ошибка JSON в {file}: {e}")
            continue

    for tpl in templates:
        cursor.execute("""
            INSERT INTO task_templates
            (textbook_id, name, question_template, answer_template, parameters, answer_type, conditions)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (textbook_id, name) DO UPDATE SET
                question_template = EXCLUDED.question_template,
                answer_template = EXCLUDED.answer_template,
                parameters = EXCLUDED.parameters,
                answer_type = EXCLUDED.answer_type,
                conditions = EXCLUDED.conditions
        """, (
            tpl['textbook_id'],
            tpl['name'],
            tpl.get('question_template', ''),
            tpl.get('answer_template', ''),
            json.dumps(tpl.get('parameters', {})),
            tpl.get('answer_type', 'numeric'),
            tpl.get('conditions', None)
        ))

conn.commit()
conn.close()

print("✅ Все шаблоны успешно загружены в базу данных.")
