from flask import Flask, flash, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, math
import sympy
import os, re, json, random
import datetime
from datetime import datetime as dt
from math_engine import MathEngine
from task_generator import TaskGenerator
from fractions import Fraction
from sympy.parsing.sympy_parser import parse_expr
from sympy import sympify, simplify, Eq
from sympy.core.sympify import SympifyError
from openai import OpenAI
from fpdf import FPDF
from flask import send_from_directory
from pathlib import Path
from flask import render_template
from weasyprint import HTML
import tempfile
from jinja2 import Template
import markdown
import psycopg2
import psycopg2.extras
import subprocess, sys, socket, atexit, time
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'


@app.after_request
def add_header(response):
    """
    Добавляем заголовки, запрещающие кеширование страниц и статических файлов.
    Это помогает избежать проблем с "зависшей" авторизацией на планшетах.
    """
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Создаем таблицу классов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grade INTEGER NOT NULL,
            letter TEXT NOT NULL,
            UNIQUE(grade, letter))
    ''')

    # Создаем таблицу пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            full_name TEXT,
            class_id INTEGER REFERENCES classes(id),
            UNIQUE(username, class_id))
    ''')

    # Создаем таблицу уроков
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER REFERENCES users(id),
            class_id INTEGER REFERENCES classes(id),
            title TEXT NOT NULL,
            date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
    ''')

    # Создаем таблицу заданий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lesson_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER REFERENCES lessons(id),
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            template_id INTEGER REFERENCES task_templates(id)
        )
    ''')

    # Создаем таблицу предметов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT)
    ''')

    # Создаем таблицу вариантов заданий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS student_task_variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER REFERENCES lessons(id),
            user_id INTEGER REFERENCES users(id),
            task_id INTEGER REFERENCES lesson_tasks(id),
            variant_data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(lesson_id, user_id, task_id))
    ''')

    # Создаем таблицу ответов учеников
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS student_answers (
            task_id INTEGER REFERENCES lesson_tasks(id),
            user_id INTEGER REFERENCES users(id),
            answer TEXT NOT NULL,
            is_correct BOOLEAN NOT NULL,
            answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (task_id, user_id))
    ''')

    # Создаем таблицу учебников
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS textbooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            grade INTEGER NOT NULL,
            UNIQUE(title, grade))
    ''')

    # Создаем таблицу шаблонов заданий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS task_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            textbook_id INTEGER REFERENCES textbooks(id),
            name TEXT NOT NULL,
            question_template TEXT NOT NULL,
            answer_template TEXT NOT NULL,
            parameters TEXT NOT NULL,
            conditions TEXT,  
            answer_type TEXT DEFAULT 'numeric',  
            UNIQUE(textbook_id, name))
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS lesson_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        question_template TEXT NOT NULL,
        answer_template TEXT NOT NULL,
        parameters TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')


    # В функции init_db(), после создания таблиц:
    cursor.execute("SELECT COUNT(*) FROM textbooks")
    if cursor.fetchone()[0] == 0:
        # Добавляем тестовые учебники
        textbooks = [
            ('Макарычев', 'Алгебра для 5 класса', 5),
            ('Мордкович', 'Алгебра для 7-9 классов', 7),
            ('Атанасян', 'Геометрия 7-9 классы', 7)
        ]
        
        for title, description, grade in textbooks:
            cursor.execute(
                "INSERT INTO textbooks (title, description, grade) VALUES (%s, %s, %s)",
                (title, description, grade)
            )
        
        conn.commit()
    # Добавляем тестовые данные
    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            # Тестовые классы
            for grade in [5, 6, 7, 8, 9, 10, 11]:
                for letter in ['А', 'Б', 'В', 'Г']:
                    cursor.execute(
                        "INSERT OR IGNORE INTO classes (grade, letter) VALUES (%s, %s)",
                        (grade, letter)
                    )
            
            # Тестовый учитель
            cursor.execute(
                "INSERT INTO users (username, password, role, full_name) VALUES (%s, %s, %s, %s)",
                ('teacher1', generate_password_hash('teacher123'), 'teacher', 'Иванова Мария Сергеевна')
            )
            
            # Тестовые ученики
            test_students = [
                ('student1', 'student123', '6В', 'Петров Петр'),
                ('student2', 'student123', '6В', 'Сидорова Анна'),
                ('student3', 'student123', '6Г', 'Кузнецов Алексей')
            ]
            
            for username, password, class_name, full_name in test_students:
                grade = int(class_name[:-1])
                letter = class_name[-1]
                
                # Получаем class_id перед использованием
                cursor.execute(
                    "SELECT id FROM classes WHERE grade = %s AND letter = %s",
                    (grade, letter)
                )
                class_row = cursor.fetchone()
                if class_row:
                    class_id = class_row[0]
                    
                    cursor.execute(
                        "INSERT INTO users (username, password, role, full_name, class_id) VALUES (%s, %s, %s, %s, %s)",
                        (username, generate_password_hash(password), 'student', full_name, class_id)
                    )
            
            # Тестовый предмет
            cursor.execute(
                "INSERT INTO subjects (name, description) VALUES (%s, %s)",
                ('Математика', 'Алгебра и геометрия 6 класс')
            )
            
            # Тестовый учебник
            cursor.execute(
                "INSERT INTO textbooks (title, description, grade) VALUES (%s, %s, %s)",
                ('Макарычев', 'Алгебра для 5 класса', 5)
            )
            
            # Базовые шаблоны для учебника
            templates = [
                ('Сложение', '{A} + {B} = %s', '{A} + {B}', '{"A": {"min": 1, "max": 10}, "B": {"min": 1, "max": 10}}'),
                ('Вычитание', '{A} - {B} = %s', '{A} - {B}', '{"A": {"min": 1, "max": 20}, "B": {"min": 1, "max": 10}}'),
                ('Умножение', '{A} × {B} = %s', '{A} * {B}', '{"A": {"min": 1, "max": 10}, "B": {"min": 1, "max": 10}}'),
                ('Деление', '{A} ÷ {B} = %s', '{A} / {B}', '{"A": {"min": 1, "max": 50}, "B": {"min": 1, "max": 10}}'),
                ('Уравнение', 'Решите: {A}x + {B} = {C}', '({C} - {B}) / {A}', '{"A": {"min": 1, "max": 5}, "B": {"min": 1, "max": 20}, "C": {"min": 10, "max": 50}}')
            ]
            
            for name, question, answer, params in templates:
                cursor.execute(
                    "INSERT INTO task_templates (textbook_id, name, question_template, answer_template, parameters) VALUES (1, %s, %s, %s, %s)",
                    (name, question, answer, params)
                )
            
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Ошибка при инициализации БД: {e}")
    finally:
        conn.close()



def get_db():
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost")
    )
    conn.autocommit = True
    return conn

@app.route('/')
def home():
    if 'user_id' in session:
        if session['role'] == 'student':
            return redirect(url_for('student_dashboard'))
        else:
            return redirect(url_for('teacher_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['full_name'] = user['full_name']
            
            if user['role'] == 'student':
                return redirect(url_for('student_dashboard'))
            else:
                return redirect(url_for('teacher_dashboard'))
        else:
            return render_template('auth.html', error="Неверное имя пользователя или пароль")
    
    return render_template('auth.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/student/dashboard')
def student_dashboard():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM subjects")
    subjects = cursor.fetchall()
    conn.close()
    
    return render_template('student_dashboard.html', 
                         full_name=session['full_name'],
                         subjects=subjects)

@app.route('/teacher/dashboard')
def teacher_dashboard():
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))
    
    return render_template('teacher_dashboard.html', 
                         full_name=session['full_name'])


@app.route('/teacher/get_lessons')
def get_lessons():
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401
    
    class_full = request.args.get('grade')  # Формат "6В"
    grade = class_full[:-1]  # "6"
    letter = class_full[-1]  # "В"
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Находим ID класса
        cursor.execute("SELECT id FROM classes WHERE grade = %s AND letter = %s", (grade, letter))
        class_id = cursor.fetchone()
        
        if not class_id:
            return jsonify({'lessons': []})
        
        # Получаем уроки для этого класса
        cursor.execute('''
            SELECT l.id, l.title, l.date 
            FROM lessons l
            WHERE l.class_id = %s AND l.teacher_id = %s
            ORDER BY l.date DESC
        ''', (class_id[0], session['user_id']))
        
        lessons = cursor.fetchall()
        return jsonify({
            'lessons': [dict(lesson) for lesson in lessons]
        })
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()



@app.route('/teacher/edit_lesson/<int:lesson_id>')
def edit_lesson(lesson_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))

    conn = get_db()  # Получаем соединение
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Получаем информацию об уроке
        cursor.execute('''
            SELECT l.id, l.title, l.date, c.grade, c.letter 
            FROM lessons l
            JOIN classes c ON l.class_id = c.id
            WHERE l.id = %s AND l.teacher_id = %s
        ''', (lesson_id, session['user_id']))
        lesson = cursor.fetchone()
        
        if not lesson:
            cursor.close()
            return redirect(url_for('teacher_dashboard'))

        # Получаем задания урока
        cursor.execute('''
            SELECT lt.id, lt.template_id, lt.variant_number, tt.name, tt.question_template
            FROM lesson_tasks lt
            JOIN task_templates tt ON lt.template_id = tt.id
            WHERE lt.lesson_id = %s
        ''', (lesson_id,))
        tasks = cursor.fetchall()
        
        # Получаем все учебники и шаблоны уроков
        cursor.execute('SELECT * FROM textbooks ORDER BY id, title')
        textbooks = cursor.fetchall()
        cursor.execute('SELECT * FROM lesson_templates')
        lesson_templates = cursor.fetchall()
        
        cursor.close()
        return render_template(
            'edit_lesson.html',
            lesson=dict(lesson),
            tasks=[dict(task) for task in tasks],
            textbooks=[dict(tb) for tb in textbooks],
            lesson_templates=[dict(tpl) for tpl in lesson_templates]
        )
    finally:
        conn.close()


@app.route('/teacher/conduct_lesson/<int:lesson_id>')
def conduct_lesson(lesson_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Получаем информацию об уроке
        cursor.execute('''
            SELECT l.id, l.title, l.date, c.grade, c.letter 
            FROM lessons l
            JOIN classes c ON l.class_id = c.id
            WHERE l.id = %s AND l.teacher_id = %s
        ''', (lesson_id, session['user_id']))
        
        lesson = cursor.fetchone()
        if not lesson:
            return redirect(url_for('teacher_dashboard'))
        
        # Получаем список учеников класса
        cursor.execute('''
            SELECT u.id, u.full_name
            FROM users u
            JOIN classes c ON u.class_id = c.id
            JOIN lessons l ON l.class_id = c.id
            WHERE l.id = %s AND u.role = 'student'
            ORDER BY u.full_name
        ''', (lesson_id,))
        students = cursor.fetchall()
        
        # Получаем задания урока
        cursor.execute('''
            SELECT id, question FROM lesson_tasks
            WHERE lesson_id = %s
            ORDER BY id
        ''', (lesson_id,))
        tasks = cursor.fetchall()
        
        return render_template('conduct_lesson.html',
                            lesson=dict(lesson),
                            students=students,
                            tasks=tasks)
    except Exception as e:
        print(f"Error: {e}")
        return "Произошла ошибка", 500
    finally:
        conn.close()

@app.route('/teacher/create_lesson', methods=['POST'])
def create_lesson():
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    class_full = data['grade']  # Формат "6В"
    
    try:
        grade = int(class_full[:-1])  # "6"
        letter = class_full[-1]       # "В"
    except:
        return jsonify({'error': 'Invalid class format'}), 400
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Находим ID класса
        cursor.execute("SELECT id FROM classes WHERE grade = %s AND letter = %s", (grade, letter))
        class_id = cursor.fetchone()
        
        if not class_id:
            return jsonify({'error': 'Class not found'}), 404
        
        # Создаем урок
        cursor.execute('''
            INSERT INTO lessons (teacher_id, class_id, title, date)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        ''', (
            session['user_id'],
            class_id[0],
            data['title'],
            data['date']
        ))
        lesson_id = cursor.fetchone()[0]
        conn.commit()
        
        return jsonify({
            'success': True,
            'lesson_id': lesson_id
        })
    except Exception as e:
        conn.rollback()
        print(f"Error creating lesson: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/teacher/update_lesson/<int:lesson_id>', methods=['POST'])
def update_lesson(lesson_id):
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        for task in data['tasks']:
            if task['id']:
                cursor.execute('''
                    UPDATE lesson_tasks 
                    SET question = %s, answer = %s, template_id = %s
                    WHERE id = %s AND lesson_id = %s
                ''', (
                    task['question'], 
                    task['answer'],
                    task.get('template_id'),  # Новое поле
                    task['id'], 
                    lesson_id
                ))
            else:
                cursor.execute('''
                    INSERT INTO lesson_tasks 
                    (lesson_id, question, answer, template_id)
                    VALUES (%s, %s, %s, %s)
                ''', (
                    lesson_id, 
                    task['question'], 
                    task['answer'],
                    task.get('template_id')  # Новое поле
                ))
                task['id'] = cursor.lastrowid
        
        conn.commit()
        return jsonify({'success': True, 'tasks': data['tasks']})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/teacher/delete_task/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Проверяем, что задание принадлежит учителю
        cursor.execute('''
            DELETE FROM lesson_tasks 
            WHERE id = %s AND lesson_id IN (
                SELECT id FROM lessons WHERE teacher_id = %s
            )
        ''', (task_id, session['user_id']))
        
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/teacher/manage_students')
def manage_students():
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM classes ORDER BY grade, letter")
    classes = cursor.fetchall()
    conn.close()
    
    return render_template('manage_students.html', classes=classes)

@app.route('/teacher/get_students')
def get_students():
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401
    
    class_id = request.args.get('class_id')
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute('''
        SELECT id, username, full_name, grade FROM users 
        WHERE role = 'student' AND class_id = %s
        ORDER BY full_name
    ''', (class_id,))
    students = cursor.fetchall()
    conn.close()
    
    return jsonify({
        'students': [dict(student) for student in students]
    })

@app.route('/teacher/add_student', methods=['POST'])
def add_student():
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute('''
            INSERT INTO users (username, password, role, full_name, class_id)
            VALUES (%s, %s, 'student', %s, %s)
        ''', (
            data['username'],
            generate_password_hash(data['password']),
            data['full_name'],
            data['class_id']
        ))
        conn.commit()
        return jsonify({'success': True})
    except sqlite3.IntegrityError as e:
        return jsonify({'success': False, 'error': 'Логин уже существует'})
    finally:
        conn.close()

@app.route('/teacher/delete_student/<int:student_id>', methods=['DELETE'])
def delete_student(student_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("DELETE FROM users WHERE id = %s AND role = 'student'", (student_id,))
        conn.commit()
        return jsonify({'success': cursor.rowcount > 0})
    finally:
        conn.close()


@app.route('/student/lessons')
def student_lessons():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Получаем класс ученика
        cursor.execute("SELECT class_id FROM users WHERE id = %s", (session['user_id'],))
        class_id = cursor.fetchone()
        
        if not class_id:
            return "У вас не указан класс", 400
        
        class_id = class_id[0]
        
        # Получаем уроки для этого класса
        cursor.execute('''
            SELECT l.id, l.title, l.date, u.full_name as teacher_name 
            FROM lessons l
            JOIN users u ON l.teacher_id = u.id
            WHERE l.class_id = %s
            ORDER BY l.date DESC
        ''', (class_id,))
        lessons = cursor.fetchall()
        
        return render_template('student_lessons.html', 
                            lessons=lessons,
                            full_name=session['full_name'])
    except Exception as e:
        print(f"Error: {e}")
        return "Произошла ошибка", 500
    finally:
        conn.close()


@app.route('/lesson/<int:lesson_id>')
def start_lesson(lesson_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    

    
    user_id = session['user_id']
    student_mark = infer_student_mark(user_id)
    print("⚡ student_mark для user_id", user_id, "=", student_mark)
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    print("Запрос урока:", lesson_id, "Текущий пользователь:", user_id, "Роль:", session.get("role"))

    
    try:
        # Проверка доступа для ученика
        if session['role'] == 'student':
            cursor.execute('''
                SELECT 1 FROM lessons l
                JOIN users u ON l.class_id = u.class_id
                WHERE u.id = %s AND l.id = %s
            ''', (user_id, lesson_id))
            if not cursor.fetchone():
                return redirect(url_for('student_lessons'))
        
        # Получаем информацию об уроке
        cursor.execute('''
            SELECT l.title, l.date, u.full_name as teacher_name
            FROM lessons l
            JOIN users u ON l.teacher_id = u.id
            WHERE l.id = %s
        ''', (lesson_id,))
        lesson = cursor.fetchone()
        
        if not lesson:
            return redirect(url_for('student_lessons'))
        
        # Получаем задания урока
        cursor.execute('''
            SELECT id, question, answer, template_id
            FROM lesson_tasks
            WHERE lesson_id = %s
            ORDER BY id
        ''', (lesson_id,))
        base_tasks = cursor.fetchall()

        print("Задания урока base_tasks:", base_tasks)

        
        tasks = []
        
        for task in base_tasks:
            print("Обрабатываю задание:", dict(task))

            # Проверяем сохраненный вариант
            cursor.execute('''
                SELECT variant_data FROM student_task_variants
                WHERE lesson_id = %s AND user_id = %s AND task_id = %s
            ''', (lesson_id, user_id, task['id']))
            variant = cursor.fetchone()
            print('Fetched variant:', variant)
            if variant:
                print('variant_data:', variant['variant_data'], type(variant['variant_data']))
                data = variant['variant_data']
                # Обработка variant_data в зависимости от типа (str, dict, bytes)
                if isinstance(data, str):
                    try:
                        variant_data = json.loads(data)
                    except Exception:
                        variant_data = {}
                elif isinstance(data, dict):
                    variant_data = data
                elif isinstance(data, bytes):
                    try:
                        variant_data = json.loads(data.decode('utf-8'))
                    except Exception:
                        variant_data = {}
                else:
                    variant_data = {}

                question = variant_data.get('generated_question', task['question'])
                computed_answer = variant_data.get('computed_answer', '')
                params = variant_data.get('params', {})
                # Получаем answer_type из шаблона!
                if task['template_id']:
                    cursor.execute('SELECT answer_type FROM task_templates WHERE id = %s', (task['template_id'],))
                    answer_type_row = cursor.fetchone()
                    answer_type = answer_type_row['answer_type'] if answer_type_row and answer_type_row['answer_type'] else 'numeric'
                else:
                    answer_type = 'numeric'
                tasks.append({
                    'id': task['id'],
                    'question': question,
                    'correct_answer': computed_answer,
                    'params': params,
                    'answer_type': answer_type
                })
            else:
                # Генерация нового варианта через TaskGenerator
                if task['template_id']:
                    # Получаем только answer_type из task_templates
                    cursor.execute('SELECT answer_type FROM task_templates WHERE id = %s', (task['template_id'],))
                    answer_type_row = cursor.fetchone()
                    answer_type = answer_type_row['answer_type'] if answer_type_row and answer_type_row['answer_type'] else 'numeric'
                    
                    # Теперь тянем остальные параметры для генерации задания
                    cursor.execute('SELECT * FROM task_templates WHERE id = %s', (task['template_id'],))
                    template_row = cursor.fetchone()
                    if template_row:
                        template_dict = dict(template_row)
                        params = template_row['parameters']
                        if isinstance(params, str):
                            params = json.loads(params)
                        template_dict['parameters'] = params
                        variant = TaskGenerator.generate_task_variant(template_dict, band=student_mark)
                        print('Сгенерированный вариант:', variant, type(variant))
                        generated_question = variant['question']
                        computed_answer = variant['correct_answer']
                        params = variant['params']
                    else:
                        generated_question = task['question']
                        computed_answer = task['answer']
                        params = {}
                else:
                    # Старые задания без шаблона
                    params = {}
                    param_matches = set(re.findall(r'\{([A-Za-z]+)\}', task['question']))
                    for param in param_matches:
                        params[param] = random.randint(1, 10)
                    generated_question = task['question']
                    for param, value in params.items():
                        generated_question = generated_question.replace(f'{{{param}}}', str(value))
                    computed_answer = "%s"
                    answer_type = 'numeric'

                # Сохраняем вариант для этого ученика
                variant_data = {
                    'params': params,
                    'generated_question': generated_question,
                    'computed_answer': computed_answer
                }
                print('Перед вставкой:', variant_data, type(variant_data))
                cursor.execute('''
                    INSERT INTO student_task_variants
                    (lesson_id, user_id, task_id, variant_data)
                    VALUES (%s, %s, %s, %s)
                ''', (lesson_id, user_id, task['id'], json.dumps(variant_data)))
                tasks.append({
                    'id': task['id'],
                    'question': generated_question,
                    'correct_answer': computed_answer,
                    'params': params,
                    'answer_type': answer_type
                })
        
        conn.commit()
        return render_template('student_lesson.html',
                            lesson=dict(lesson),
                            tasks=tasks,
                            user_id=user_id)
        
    except Exception as e:
        conn.rollback()
        print(f"Error in start_lesson: {str(e)}")  # Логируем ошибку
        return "Произошла ошибка при загрузке урока", 500
    finally:
        conn.close()


@app.route('/save_answer', methods=['POST'])
def save_answer():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    print("DEBUG /save_answer:", data)
    user_id = session['user_id']
    task_id = data['task_id']
    print("DEBUG /save_answer user_id:", session.get('user_id'))

    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Проверяем, есть ли уже ответ (НОВОЕ)
    cursor.execute('''
        SELECT answer, is_correct FROM student_answers 
        WHERE task_id = %s AND user_id = %s
    ''', (task_id, user_id))
    existing = cursor.fetchone()

    if existing:
        return jsonify({  # Возвращаем существующий ответ, а не ошибку
            'success': True,
            'already_exists': True,
            'saved_answer': existing['answer'],
            'is_correct': existing['is_correct']
        })

    # Старая логика сохранения (ОСТАЕТСЯ БЕЗ ИЗМЕНЕНИЙ)
    is_correct_val = data['is_correct']
    if isinstance(is_correct_val, str):
        is_correct_val = is_correct_val.lower() in ['true', '1', 'yes']
    elif isinstance(is_correct_val, int):
        is_correct_val = bool(is_correct_val)
    elif isinstance(is_correct_val, bool):
        pass
    else:
        is_correct_val = False

    cursor.execute('''
        INSERT INTO student_answers (task_id, user_id, answer, is_correct, answered_at)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (task_id, user_id) DO UPDATE SET
            answer = EXCLUDED.answer,
            is_correct = EXCLUDED.is_correct,
            answered_at = CURRENT_TIMESTAMP
    ''', (task_id, user_id, data['answer'], is_correct_val))

    conn.commit()
    return jsonify({'success': True, 'already_exists': False})






@app.route('/teacher/get_lesson_results/<int:lesson_id>')
def get_lesson_results(lesson_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Получаем список учеников и их ответов
        cursor.execute('''
            SELECT 
                u.id as user_id, 
                u.full_name,
                t.id as task_id,
                sa.answer,
                sa.is_correct
            FROM users u
            JOIN lessons l ON u.class_id = l.class_id
            JOIN lesson_tasks t ON t.lesson_id = l.id
            LEFT JOIN student_answers sa ON sa.task_id = t.id AND sa.user_id = u.id
            WHERE l.id = %s AND u.role = 'student'
            ORDER BY u.full_name, t.id
        ''', (lesson_id,))
        
        # Формируем структуру результатов
        results = {}
        for row in cursor.fetchall():
            user_id = row['user_id']
            if user_id not in results:
                results[user_id] = {
                    'user_id': user_id,
                    'full_name': row['full_name'],
                    'tasks': []
                }
            
            results[user_id]['tasks'].append({
                'task_id': row['task_id'],
                'answered': row['answer'] is not None,
                'is_correct': row['is_correct'] if row['is_correct'] is not None else False,
                'answer': row['answer']
            })
        
        return jsonify({
            'results': list(results.values())
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/get_student_answers/<int:lesson_id>/<int:user_id>')
def get_student_answers(lesson_id, user_id):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    cursor.execute('''
        SELECT task_id, answer, is_correct
        FROM student_answers
        WHERE user_id = %s AND task_id IN (
            SELECT id FROM lesson_tasks WHERE lesson_id = %s
        )
    ''', (user_id, lesson_id))
    
    answers = cursor.fetchall()
    return jsonify([dict(answer) for answer in answers])



@app.route('/teacher/end_lesson/<int:lesson_id>', methods=['POST'])
def end_lesson(lesson_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Здесь можно добавить логику завершения урока
    # Например, пометить урок как завершенный в базе данных
    
    return jsonify({'success': True})


@app.route('/teacher/get_student_progress/<int:lesson_id>')
def get_student_progress(lesson_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Получаем прогресс всех учеников
        cursor.execute('''
            SELECT 
                u.id as student_id,
                u.full_name,
                t.id as task_id,
                sa.answer,
                sa.is_correct
            FROM users u
            JOIN lessons l ON u.class_id = l.class_id
            JOIN lesson_tasks t ON t.lesson_id = l.id
            LEFT JOIN student_answers sa ON sa.task_id = t.id AND sa.user_id = u.id
            WHERE l.id = %s AND u.role = 'student'
            ORDER BY u.full_name, t.id
        ''', (lesson_id,))
        
        # Формируем структуру результатов
        students = {}
        for row in cursor.fetchall():
            student_id = row['student_id']
            if student_id not in students:
                students[student_id] = {
                    'student_id': student_id,
                    'full_name': row['full_name'],
                    'tasks': []
                }
            
            students[student_id]['tasks'].append({
                'task_id': row['task_id'],
                'answered': row['answer'] is not None,
                'is_correct': row['is_correct'] if row['is_correct'] is not None else False
            })
        
        # Рассчитываем прогресс для каждого студента
        result = []
        for student in students.values():
            correct_count = sum(1 for task in student['tasks'] if task['is_correct'])
            total_tasks = len(student['tasks'])
            progress = round((correct_count / total_tasks) * 100) if total_tasks > 0 else 0
            
            result.append({
                'student_id': student['student_id'],
                'full_name': student['full_name'],
                'progress': progress,
                'tasks': student['tasks']
            })
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/teacher/manage_tasks')
def manage_tasks():
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))
    
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('SELECT * FROM textbooks ORDER BY grade, title')
        textbooks = cursor.fetchall()
        cursor.close()
        return render_template('manage_tasks.html', 
                            full_name=session['full_name'],
                            textbooks=textbooks)
    except Exception as e:
        print(f"Error fetching textbooks: {e}")
        return "Произошла ошибка при загрузке учебников", 500
    finally:
        conn.close()


@app.route('/teacher/manage_tasks/<int:textbook_id>')
def textbook_tasks(textbook_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))
    
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Получаем учебник
        cursor.execute('SELECT * FROM textbooks WHERE id = %s', (textbook_id,))
        textbook = cursor.fetchone()
        if not textbook:
            cursor.close()
            flash('Учебник не найден', 'error')
            return redirect(url_for('manage_tasks'))
        
        # Получаем шаблоны заданий с нумерацией
        cursor.execute('''
            SELECT *, 
                   ROW_NUMBER() OVER (ORDER BY id) as task_number 
            FROM task_templates 
            WHERE textbook_id = %s 
            ORDER BY id
        ''', (textbook_id,))
        templates = cursor.fetchall()
        
        cursor.close()
        return render_template(
            'textbook_tasks.html', 
            full_name=session['full_name'],
            textbook=dict(textbook),
            templates=templates
        )
    except Exception as e:
        print(f"Error loading textbook tasks: {e}")
        flash('Произошла ошибка при загрузке заданий', 'error')
        return redirect(url_for('manage_tasks'))
    finally:
        conn.close()


@app.route('/teacher/add_task_template', methods=['POST'])
def add_task_template():
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('''
            INSERT INTO task_templates 
            (textbook_id, name, question_template, answer_template, parameters)
            VALUES (%s, %s, %s, %s, %s)
        ''', (
            data['textbook_id'],
            data['name'],
            data['question_template'],
            data['answer_template'],
            json.dumps(data['parameters'])
        ))
        
        conn.commit()
        return jsonify({
            'success': True,
            'template_id': cursor.lastrowid
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/teacher/update_task_template/<int:template_id>', methods=['POST'])
def update_task_template(template_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('''
            UPDATE task_templates SET
                name = %s,
                question_template = %s,
                answer_template = %s,
                parameters = %s
            WHERE id = %s
        ''', (
            data['name'],
            data['question_template'],
            data['answer_template'],
            json.dumps(data['parameters']),
            template_id
        ))
        
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/teacher/delete_task_template/<int:template_id>', methods=['DELETE'])
def delete_task_template(template_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('DELETE FROM task_templates WHERE id = %s', (template_id,))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()
        

@app.route('/teacher/add_textbook', methods=['POST'])
def add_textbook():
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    title = data.get('title')
    description = data.get('description')
    grade = data.get('grade')
    
    if not title or not grade:
        return jsonify({'success': False, 'error': 'Название и класс обязательны'})
    
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('''
            INSERT INTO textbooks (title, description, grade)
            VALUES (%s, %s, %s)
        ''', (title, description, grade))
        
        conn.commit()
        return jsonify({
            'success': True,
            'textbook_id': cursor.lastrowid
        })
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'error': 'Учебник с таким названием и классом уже существует'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

# Маршрут для сохранения шаблона
@app.route('/api/templates', methods=['POST'])
def save_template():
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    required_fields = ['textbook_id', 'name', 'question', 'answer', 'parameters']
    
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400

    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Проверяем, существует ли учебник
        cursor.execute(
            'SELECT 1 FROM textbooks WHERE id = %s',
            (data['textbook_id'],)
        )
        textbook = cursor.fetchone()
        if not textbook:
            cursor.close()
            return jsonify({'error': 'Textbook not found'}), 404

        # Сохраняем шаблон (используем RETURNING для получения id)
        cursor.execute('''
            INSERT INTO task_templates 
            (textbook_id, name, question_template, answer_template, parameters)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            data['textbook_id'],
            data['name'],
            data['question'],
            data['answer'],
            json.dumps(data['parameters'])
        ))
        template_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        return jsonify({
            'success': True,
            'template_id': template_id
        })
    except psycopg2.IntegrityError as e:
        conn.rollback()
        return jsonify({
            'success': False,
            'error': 'Template with this name already exists'
        }), 400
    except Exception as e:
        conn.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        conn.close()


CYR = ' абвгдеёжзийклмнопрстуфхцчшщъыьэюя'  # пробел в начале для safety
CYR_INDEX = {ch: i for i, ch in enumerate(CYR)}


def natural_key(s: str):
    s = (s or '').lower().strip()
    parts = re.findall(r'\d+|[a-zа-яё]+', s)  # числа ИЛИ буквы; . и пробелы игнорим
    key = []
    for p in parts:
        if p.isdigit():
            key.append((0, int(p)))  # числа как int
        else:
            key.append((1, tuple(CYR_INDEX.get(ch, 999) for ch in p)))  # буквы по алфавиту
    return tuple(key)


@app.route('/api/textbooks/<int:textbook_id>/templates')
def get_templates(textbook_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('''
            SELECT id, name, question_template, answer_template, parameters
            FROM task_templates
            WHERE textbook_id = %s
        ''', (textbook_id,))
        templates = [dict(t) for t in cursor.fetchall()]
        cursor.close()

        # Натуральная сортировка: 1.4 < 1.30, 1а после 1, и т.д.
        templates.sort(key=lambda t: natural_key(t['name']))

        return jsonify({'success': True, 'templates': templates})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


def get_textbook_templates(textbook_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('''
            SELECT * FROM task_templates WHERE textbook_id = %s
        ''', (textbook_id,))
        templates = cursor.fetchall()
        cursor.close()
        return jsonify({
            'success': True,
            'templates': [dict(t) for t in templates]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# Маршрут для удаления шаблона
@app.route('/api/templates/<int:template_id>', methods=['DELETE'])
def delete_templates(template_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    try:
        result = conn.execute(
            'DELETE FROM task_templates WHERE id = %s', 
            (template_id,)
        )
        conn.commit()
        
        if result.rowcount == 0:
            return jsonify({'success': False, 'error': 'Template not found'}), 404
            
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        conn.close()

@app.route('/api/templates/<int:template_id>')
def get_template(template_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    try:
        # ОТКРЫВАЕМ КУРСОР
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('''
            SELECT id, textbook_id, name, question_template, answer_template, parameters
            FROM task_templates
            WHERE id = %s
        ''', (template_id,))
        template = cursor.fetchone()
        cursor.close()

        if not template:
            return jsonify({'success': False, 'error': 'Template not found'}), 404

        return jsonify({
            'success': True,
            'template': dict(template)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


def compare_expressions(ans1, ans2):
    # Добавим * между числом и скобкой, если нужно
    import re
    def fix_mul(expr):
        # Заменяет 2(x+1) на 2*(x+1)
        return re.sub(r'(\d)(\()', r'\1*\2', expr)
    ans1 = fix_mul(ans1.replace("^", "**").replace(" ", ""))
    ans2 = fix_mul(ans2.replace("^", "**").replace(" ", ""))
    def can_parse_as_expr(s):
        # хотя бы одна буква и хотя бы один арифметический оператор
        return any(c.isalpha() for c in s) and any(op in s for op in "+-*/^")
    if can_parse_as_expr(ans1) and can_parse_as_expr(ans2):
        try:
            expr1 = parse_expr(ans1, evaluate=True)
            expr2 = parse_expr(ans2, evaluate=True)
            # Если разность упростилась до 0 — выражения эквивалентны
            return sympy.simplify(expr1 - expr2) == 0
        except Exception as e:
            # Если не удалось распарсить — fallback
            return ans1 == ans2
    else:
        return ans1 == ans2
    
@app.route('/api/generate_task', methods=['POST'])
def generate_task():
    data = request.get_json()
    template_id = data.get('template_id')
    
    conn = get_db()
    template = conn.execute('SELECT * FROM task_templates WHERE id = %s', [template_id]).fetchone()
    if not template:
        return jsonify({"error": "Template not found"}), 404

    params = json.loads(template['parameters'])
    generated_params = MathEngine.generate_parameters(params)
    
    question = template['question_template'].format(**generated_params)
    answer = MathEngine.evaluate_expression(template['answer_template'], generated_params)
    
    return jsonify({
        "question": question,
        "answer": answer,
        "params": generated_params
    })

def insert_mul_sign(expr):
    expr = re.sub(r'(\d)([a-zA-Z])', r'\1*\2', expr)
    expr = re.sub(r'(\))([a-zA-Z])', r'\1*\2', expr)
    return expr

@app.route('/api/check_answer', methods=['POST'])
def api_check_answer():
    try:
        data = request.get_json()
        print("DEBUG DATA:", data)
        user_answer = data['answer'].strip()
        correct_answer = data['correct_answer']
        answer_type = data.get('answer_type', 'numeric')

        def is_fraction(s):
            return '/' in s and len(s.split('/')) == 2

        def to_float(val):
            try:
                return float(val.replace(",", "."))
            except Exception:
                try:
                    if is_fraction(val):
                        num, denom = val.split('/')
                        return float(num) / float(denom)
                except Exception:
                    return None
            return None

        def float_to_fraction(val, max_denominator=1000):
            frac = Fraction(val).limit_denominator(max_denominator)
            return f"{frac.numerator}/{frac.denominator}"

        def parse_math_answer(ans):
            s = ans.replace(",", ".").replace("%", "").strip()
            if "_" in s:
                parts = s.split("_")
                if len(parts) == 2 and "/" in parts[1]:
                    whole = float(parts[0])
                    num, denom = parts[1].split("/")
                    return whole + float(num) / float(denom)
            if " " in s and "/" in s:
                parts = s.split(" ")
                if len(parts) == 2 and "/" in parts[1]:
                    whole = float(parts[0])
                    num, denom = parts[1].split("/")
                    return whole + float(num) / float(denom)
            if "/" in s:
                try:
                    num, denom = s.split("/")
                    return float(num) / float(denom)
                except Exception:
                    pass
            if s.startswith("sqrt(") and s.endswith(")"):
                try:
                    return math.sqrt(float(s[5:-1]))
                except:
                    pass
            if "^" in s:
                try:
                    base, exp = s.split("^")
                    return float(base) ** float(exp)
                except:
                    pass
            try:
                return float(s)
            except Exception:
                return None

        def parse_answer_list(ans):
            sep = ";" if ";" in ans else ("," if "," in ans else None)
            if sep:
                parts = [p.strip() for p in ans.split(sep)]
            else:
                parts = [ans.strip()]
            return [parse_math_answer(p) for p in parts if p]

        # --- Универсальный "умный" компаратор ---
        def check_equivalent_answers(user, correct, answer_type="string"):
            user = str(user).replace(" ", "").replace('^', '**')
            correct = str(correct).replace(" ", "").replace('^', '**')
            # Для дробей и чисел
            if answer_type in ("numeric", "дробный"):
                try:
                    # Fraction (1/2 == 2/4 == 0.5)
                    if '/' in user or '/' in correct:
                        return Fraction(user) == Fraction(correct)
                    return abs(float(user) - float(correct)) < 1e-6
                except Exception:
                    pass
            # Для списков из дробей/чисел
            if (";" in user or "," in user) and (";" in correct or "," in correct):
                user_parts = re.split(r"[;,]", user)
                correct_parts = re.split(r"[;,]", correct)
                if len(user_parts) == len(correct_parts):
                    try:
                        return all(check_equivalent_answers(u, c, answer_type) for u, c in zip(user_parts, correct_parts))
                    except Exception:
                        return False
            # Для выражений (алгебра/дроби)
            try:    
                user_expr = simplify(sympify(user))
                correct_expr = simplify(sympify(correct))
                return simplify(user_expr - correct_expr) == 0
            except Exception:
                # Фоллбэк: сравнение как строки (для простых кейсов)
                return user.lower() == correct.lower()

        # --- Интервалы и интервальные сравнения ---
        if answer_type == "interval" or (
            ";" in correct_answer and all(
                "/" in part or "." in part or part.isdigit() or part.lstrip("-").replace(".", "").isdigit()
                for part in correct_answer.split(";"))
        ):
            interval_bounds = parse_answer_list(correct_answer)
            if len(interval_bounds) == 2 and None not in interval_bounds:
                left, right = sorted(interval_bounds)
                user_val = parse_math_answer(user_answer)
                if user_val is not None and left < user_val < right:
                    return jsonify({
                        "is_correct": True,
                        "evaluated_answer": user_answer,
                        "correct_answer": correct_answer
                    })
                else:
                    return jsonify({
                        "is_correct": False,
                        "evaluated_answer": user_answer,
                        "correct_answer": correct_answer
                    })

        # --- Строковые задачи (старый механизм сохранён) ---
        if answer_type == 'string':
            ua = user_answer.strip().replace(" ", "")
            ca = correct_answer.strip().replace(" ", "")
            print(f"Debug: Comparing user answer '{ua}' with correct '{ca}'")
            # Оставляем проверку одного символа (например, знак сравнения)
            if len(ua) == 1 and len(ca) == 1:
                is_correct = ua == ca
            else:
                # Проверка как выражения
                def can_parse_as_expr(s):
                    return any(c.isalpha() for c in s) and any(op in s for op in "+-*/^")
                if can_parse_as_expr(ua) and can_parse_as_expr(ca):
                    try:
                        ua_mod = insert_mul_sign(ua)
                        ca_mod = insert_mul_sign(ca)
                        expr1 = parse_expr(ua_mod.replace("^", "**"))
                        expr2 = parse_expr(ca_mod.replace("^", "**"))
                        is_correct = simplify(expr1 - expr2) == 0
                    except Exception as e:
                        is_correct = ua.lower() == ca.lower()
                else:
                    is_correct = ua.lower() == ca.lower()
            return jsonify({"is_correct": is_correct, "correct_answer": correct_answer})

        # --- Алгебраические задачи ---
        if answer_type == 'algebraic':
            try:
                ua_mod = insert_mul_sign(user_answer)
                ca_mod = insert_mul_sign(correct_answer)
                expr1 = simplify(sympify(ua_mod.replace("^", "**")))
                expr2 = simplify(sympify(ca_mod.replace("^", "**")))
                is_correct = simplify(expr1 - expr2) == 0
            except Exception:
                def normalize_string_answer(answer: str) -> str:
                    import re
                    return re.sub(r'\s+', '', answer).replace('\u200b', '').replace('\xa0', '').strip().lower()

                if answer_type == "string":
                    is_correct = normalize_string_answer(user_answer) == normalize_string_answer(correct_answer)
                else:
                    is_correct = user_answer == correct_answer
            return jsonify({
                "is_correct": is_correct,
                "correct_answer": correct_answer
            })
        


        # --- Основная универсальная проверка: списки дробей и чисел ---
        user_vals = parse_answer_list(user_answer)
        correct_vals = parse_answer_list(correct_answer)
        if len(user_vals) != len(correct_vals) or any(v is None for v in user_vals):
            return jsonify({
                "is_correct": False,
                "evaluated_answer": user_answer,
                "correct_answer": correct_answer
            })
        if any(v is None for v in correct_vals):
            return jsonify({"is_correct": False, "error": "Ошибка генерации правильного ответа"})

        is_correct = all(round(u, 4) == round(c, 4) for u, c in zip(user_vals, correct_vals))
        return jsonify({
            "is_correct": is_correct,
            "evaluated_answer": user_answer,
            "correct_answer": correct_answer
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500



# В app.py добавить новый маршрут
@app.route('/api/generate_from_template/<int:template_id>')
def generate_from_template(template_id):
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('SELECT * FROM task_templates WHERE id = %s', [template_id])
        template = cursor.fetchone()
        cursor.close()

        if not template:
            return jsonify({"error": "Template not found"}), 404

        template_dict = dict(template)
        # В parameters лежит строка в JSON, нужно распарсить
        if isinstance(template_dict['parameters'], str):
            template_dict['parameters'] = json.loads(template_dict['parameters'])
        else:
            template_dict['parameters'] = template_dict['parameters']  # может быть уже dict (jsonb)
        
        # Генерируем вариант
        variant = TaskGenerator.generate_task_variant(template_dict)
        print('Сгенерированный вариант:', variant, type(variant))
        
        return jsonify(variant)
    except Exception as e:
        print('Ошибка генерации задания:', e)
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# В app.py добавляем новые маршруты и изменяем существующие

@app.route('/teacher/lesson_templates')
def manage_lesson_templates():
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))
    
    conn = get_db()
    try:
        # Получаем все учебники для выбора шаблонов
        textbooks = conn.execute('SELECT * FROM textbooks ORDER BY grade, title').fetchall()
        return render_template('lesson_templates.html',
                            full_name=session['full_name'],
                            textbooks=textbooks)
    except Exception as e:
        print(f"Error: {e}")
        return "Произошла ошибка", 500
    finally:
        conn.close()

@app.route('/api/lesson_templates', methods=['POST'])
def save_lesson_template():
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    required_fields = ['name', 'question_template', 'answer_template', 'parameters']
    
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400

    conn = get_db()
    try:
        # Сохраняем шаблон для урока (без привязки к учебнику)
        conn.execute('''
            INSERT INTO lesson_templates 
            (name, question_template, answer_template, parameters)
            VALUES (%s, %s, %s, %s)
        ''', (
            data['name'],
            data['question_template'],
            data['answer_template'],
            json.dumps(data['parameters'])
        ))
        
        conn.commit()
        return jsonify({
            'success': True,
            'template_id': conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        })
    except Exception as e:
        conn.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        conn.close()

@app.route('/api/lesson_templates/<int:template_id>')
def get_lesson_template(template_id):
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db()
    try:
        template = conn.execute('''
            SELECT * FROM lesson_templates WHERE id = %s
        ''', (template_id,)).fetchone()

        if not template:
            return jsonify({'error': 'Template not found'}), 404

        return jsonify({
            'success': True,
            'template': dict(template)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/teacher/bulk_delete_templates', methods=['POST'])
def bulk_delete_templates():
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    textbook_id = data['textbook_id']
    template_ids = data['template_ids']
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Удаляем только шаблоны, принадлежащие указанному учебнику
        placeholders = ','.join(['%s'] * len(template_ids))
        cursor.execute(f'''
            DELETE FROM task_templates 
            WHERE id IN ({placeholders}) AND textbook_id = %s
        ''', (*template_ids, textbook_id))
        
        deleted_count = cursor.rowcount
        conn.commit()
        
        return jsonify({
            'success': True,
            'deleted_count': deleted_count
        })
    except Exception as e:
        conn.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        conn.close()

def float_to_fraction(val, max_denominator=1000):
    """Преобразует float в несократимую обыкновенную дробь."""
    frac = Fraction(val).limit_denominator(max_denominator)
    return f"{frac.numerator}/{frac.denominator}"
                

@app.route('/api/generate_homework/<int:lesson_id>/<int:student_id>', methods=['POST'])
def generate_homework(lesson_id, student_id):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Получаем ответы ученика
    cursor.execute('''
        SELECT t.question, sa.answer, sa.is_correct, v.variant_data
        FROM student_answers sa
        JOIN lesson_tasks t ON t.id = sa.task_id
        LEFT JOIN student_task_variants v ON v.task_id = t.id AND v.user_id = sa.user_id
        WHERE sa.user_id = %s AND t.lesson_id = %s
    ''', (student_id, lesson_id))

    rows = cursor.fetchall()
    if not rows:
        return jsonify({'error': 'Нет ответов'}), 404

    wrong_data = ""
    for row in rows:
        if not row['is_correct']:
            # Восстанавливаем сгенерированный вопрос для этого ученика
            variant = json.loads(row['variant_data']) if row['variant_data'] else {}
            question = variant.get('generated_question', row['question'])  # если нет, то fallback на шаблон
            answer = row['answer']
            correct_answer = variant.get('computed_answer', 'неизвестно')
            wrong_data += f"{question} = {answer} ❌ (нужно: {correct_answer})\n"

    if not wrong_data:
        return jsonify({'text': 'Ученик не допустил ошибок. ДЗ не требуется.'})

    # Новый синтаксис OpenAI API
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    prompt = rf"""
Ученик сделал ошибки:

{wrong_data}

Составь домашнее задание по следующей структуре:

1. Вступление. Обратись к ученику добрым тоном. Объясни, какие ошибки он допустил, и что мы сейчас разберём вместе.

2. Для каждой задачи с ошибкой:
    - Покажи саму задачу и ответ ученика
    - Объясни, в чём ошибка (на понятном языке). И разбери ошибку подробно, по шагам. 
    - Разбери аналогичный пример с пошаговым объяснением (без использования LaTeX)
    - Дай 1 новое похожих задания без решения

3. Заверши поддержкой и мотивацией (например: "У тебя точно получится!").

Форматируй красиво: заголовки **жирным**, задачи в блоках, шаги с отступами. Не используй \[ \] или \( \) — формулы пиши текстом.
"""

    chat_response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )

    content = chat_response.choices[0].message.content

    # Генерация PDF
    rendered = render_template("homework_template.html", content=content)
    filepath = f"homeworks/homework_{lesson_id}_{student_id}.pdf"
    os.makedirs("homeworks", exist_ok=True)
    HTML(string=rendered).write_pdf(filepath)

    return jsonify({'url': f"/{filepath}"})

@app.route('/homeworks/<path:filename>')
def serve_homework(filename):
    return send_from_directory('homeworks', filename)
               
@app.route('/api/generate_homework_class/<int:lesson_id>', methods=['POST'])
def generate_homework_class(lesson_id):
    print("Генерация ДЗ для класса, lesson_id:", lesson_id)
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Получаем всех учеников класса
    cursor.execute('''
        SELECT u.id, u.full_name
        FROM users u
        JOIN lessons l ON u.class_id = l.class_id
        WHERE l.id = %s AND u.role = 'student'
        ORDER BY u.full_name
    ''', (lesson_id,))
    students = cursor.fetchall()

    if not students:
        return jsonify({'error': 'Нет учеников в классе'}), 404

    # Собираем индивидуальные отчеты
    homework_blocks = []
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    for student in students:
        print("Обрабатываю ученика:", student)
        student_id = student['id']
        full_name = student['full_name']

        # Получаем ошибки по аналогии с generate_homework
        cursor.execute('''
            SELECT t.id as task_id, t.question, sa.answer, sa.is_correct, v.variant_data
            FROM lesson_tasks t
            LEFT JOIN student_answers sa ON sa.task_id = t.id AND sa.user_id = %s
            LEFT JOIN student_task_variants v ON v.task_id = t.id AND v.user_id = %s
            WHERE t.lesson_id = %s
        ''', (student_id, student_id, lesson_id))
        rows = cursor.fetchall()
        print("Ответы ученика:", rows)

        wrong_data = ""
        data = request.get_json(silent=True) or {}
        exclude = set(str(x) for x in data.get("exclude", []))

        wrong_data = ""
        for row in rows:
            if (row['is_correct'] == False or row['answer'] is None) and str(row['task_id']) not in exclude:
                variant = json.loads(row['variant_data']) if row['variant_data'] else {}
                question = variant.get('generated_question', row['question'])
                answer = row['answer'] if row['answer'] is not None else "—"
                correct_answer = variant.get('computed_answer', 'неизвестно')
                wrong_data += f"{question} = {answer} ❌ (нужно: {correct_answer})\n"
        print("wrong_data:", wrong_data)

        if not wrong_data:
            # Если нет ошибок — похвала
            student_hw = f"<h2>Домашка для {full_name}</h2>\n<p>Молодец! Ошибок нет — так держать 🎉</p>"
        else:
            prompt = rf"""
Ты — дружелюбный учитель. Проанализируй ошибки ученика и создай индивидуальное домашнее задание в Markdown-формате по структуре:

# Домашнее задание для {full_name}

Вот ошибки ученика:
{wrong_data}

Краткое приветствие и мотивация.

## Задача 1

**Условие:** ...  
**Ответ ученика:** ...  
**Правильный ответ:** ...  

**В чём ошибка:**  
Объясни кратко.

**Как решать:**
1. Шаг 1...
2. Шаг 2...

**Аналогичный пример:**
Пошаговое объяснение похожей задачи.

**Новые задания:**
- Задание 1
- Задание 2

## Задача 2
(и так далее...)

В конце — мотивация и пожелание удачи.

**Важно:**
- Используй Markdown (`#`, `##`, `**` для выделения, списки).
- Между логическими блоками делай пустые строки.
- Не вставляй формулы в виде LaTeX или кода! Дроби пиши через слэш (например, 3 1/2).
"""
            chat_response = client.chat.completions.create(
                model="gpt-4.1-mini",  # или другая твоя модель
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            hw_text = chat_response.choices[0].message.content
            hw_html = markdown.markdown(hw_text, extensions=['extra', 'nl2br', 'sane_lists'])
            student_hw = f"<div style='page-break-before: always'></div><h2>Домашка для {full_name}</h2>\n{hw_html}"

        homework_blocks.append(student_hw)

    # Собираем единый HTML и рендерим PDF
    html = render_template('homework_class_template.html', blocks=homework_blocks)
    filepath = f"homeworks/homework_class_{lesson_id}.pdf"
    os.makedirs("homeworks", exist_ok=True)
    HTML(string=html).write_pdf(filepath)

    # Отдаем PDF
    return send_from_directory('homeworks', f"homework_class_{lesson_id}.pdf", as_attachment=True)

@app.route('/teacher/set_grade', methods=['POST'])
def set_grade():
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    student_id = data.get('student_id')
    grade = data.get('grade')

    if grade not in [2, 3, 4, 5]:
        return jsonify({'error': 'Invalid grade'}), 400

    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute('''
            UPDATE users SET grade = %s WHERE id = %s AND role = 'student'
        ''', (grade, student_id))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()


import openai

@app.route('/api/ai_step_dialog', methods=['POST'])
def ai_step_dialog():
    data = request.get_json()
    user_id = data.get("user_id")
    question = data.get("question")
    history = data.get("history", [])

    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT grade FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    if row and row["grade"] is not None:
        mark = int(row["grade"])
        if mark in (4, 5):
            # Для сильных учеников — не давать ИИ-подсказки
            return jsonify({
                "question": "",
                "options": [],
                "correct_index": None,
                "explanation": ""
            })
        elif mark == 2:
            student_level = "weak"
        elif mark == 3:
            student_level = "medium"
        else:
            student_level = "medium"
    else:
        student_level = "medium"

    level_text = {
        "weak": "Ученик часто ошибается и слабо понимает материал. Пиши максимально просто, шаг за шагом.",
        "medium": "Ученик иногда ошибается, объясняй достаточно подробно, но не слишком просто.",
        "strong": "Ученик хорошо разбирается, можно предлагать более сложные варианты, минимум пояснений."
    }[student_level]

    # --- Формируем промпт для OpenAI ---
    prompt = f"""
    Ты — доброжелательный репетитор математики. Ученик только что ошибся в задании "{question}".
    {level_text}
    Сгенерируй следующий шаг пошагового мини-квеста для обучения:
    1. Придумай понятный вопрос (коротко), который побуждает подумать, что делать дальше по решению задачи.
    2. Дай 2-4 варианта ответа. Только один из них должен быть правильным.
    3. Укажи, какой индекс правильного варианта.
    4. Объясни (кратко и понятно!), почему этот шаг верный или что стоит сделать.
    Формат строго:
    {{
        "question": "...",
        "options": ["...", "...", "..."],
        "correct_index": 1,
        "explanation": "..."
    }}
    Уровень ученика: {student_level}.
    История шагов: {history if history else "шаг первый, начало решения"}
    Не объясняй полностью, а только следующий шаг!
    """

    # --- Запрос к OpenAI ---
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",  # Или другой твой доступный
            messages=[{"role": "user", "content": prompt}],
            max_tokens=350,
            temperature=0.3
        )
        # Парсим json из ответа
        import json
        content = response.choices[0].message.content
        # Иногда GPT оборачивает в ```
        content = content.replace('```json', '').replace('```', '').strip()
        data = json.loads(content)
        return jsonify(data)
    except Exception as e:
        print("Ошибка OpenAI:", e)
        return jsonify({'error': str(e)}), 500

    
@app.route('/api/ai_full_solution', methods=['POST'])
def ai_full_solution():
    data = request.get_json()
    question = data.get("question")
    correct_answer = data.get("correct_answer")
    # user_id можно использовать для логов, если надо

    prompt = f"""
    Ты — доброжелательный репетитор по математике. Дай полный подробный разбор решения задачи для ученика:
    "{question}"
    Дай пошаговое объяснение, чтобы ученик понял ход рассуждений. 
    В конце обязательно укажи правильный ответ
    Не упоминай, что ты ИИ.
    Все математические формулы оформляй в LaTeX:
Не используй одинарные квадратные скобки [ ... ] для формул.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
            temperature=0.2
        )
        content = response.choices[0].message.content
        return jsonify({"solution": content})
    except Exception as e:
        print("Ошибка OpenAI:", e)
        return jsonify({"solution": "Ошибка ИИ: не удалось получить решение."}), 500


@app.route('/dispute_answer', methods=['POST'])
def dispute_answer():
    data = request.get_json()
    task_id = data.get("task_id")
    student_answer = data.get("answer", "").strip()
    correct_answer = data.get("correct_answer", "").strip()

    if student_answer == correct_answer:
        user_id = session.get("user_id")

        try:
            # Отправляем на /save_answer
            requests.post("http://127.0.0.1:5000/save_answer", json={
                "task_id": task_id,
                "answer": student_answer,
                "is_correct": True,
                "user_id": user_id
            })
        except Exception as e:
            print("Ошибка при сохранении через /save_answer:", e)

        return jsonify({"result": "accepted", "message": "Ответ засчитан как правильный."})
    else:
        return jsonify({"result": "rejected", "message": "Ответ действительно отличается."})


def infer_student_mark(user_id: int) -> int:
    """
    Грубая авто-оценка 2..5 по доле правильных ответов за всё время.
    <25% → 2; 25–50% → 3; 50–75% → 4; ≥75% → 5.
    Если истории нет — вернём 3 (средний).
    """
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("""
            SELECT 
                COUNT(*) AS total,
                SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) AS correct
            FROM student_answers
            WHERE user_id = %s
        """, (user_id,))
        row = cursor.fetchone()
        total = row['total'] or 0
        correct = row['correct'] or 0
        if total == 0:
            return 3
        rate = correct / total
        if rate < 0.25:
            return 2
        elif rate < 0.50:
            return 3
        elif rate < 0.75:
            return 4
        else:
            return 5
    finally:
        conn.close()



@app.route('/api/generate_retry_task/<int:task_id>')
def generate_retry_task(task_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    conn = get_db()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # --- Проверка: есть ли уже retry-вариант ---
        cursor.execute('''
            SELECT variant_data FROM student_task_variants
            WHERE lesson_id = (
                SELECT lesson_id FROM lesson_tasks WHERE id = %s
            )
            AND user_id = %s
            AND task_id = %s
            AND variant_type = 'retry'
        ''', (task_id, user_id, task_id))
        retry_variant = cursor.fetchone()

        if retry_variant:
            data = retry_variant['variant_data']
            if isinstance(data, str):
                data = json.loads(data)
            return jsonify(data)

        # --- Если нет, генерируем новый ---
        cursor.execute('''
            SELECT lt.*, tt.question_template, tt.answer_template, tt.parameters, tt.conditions, tt.answer_type
            FROM lesson_tasks lt
            LEFT JOIN task_templates tt ON lt.template_id = tt.id
            WHERE lt.id = %s
        ''', (task_id,))
        task = cursor.fetchone()
        if not task:
            return jsonify({'error': 'Task not found'}), 404

        params = task['parameters']
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except:
                params = {}
        elif not isinstance(params, dict):
            params = {}

        template_dict = {
            'id': task['template_id'],
            'question_template': task['question_template'] or task['question'],
            'answer_template': task['answer_template'] or task['answer'],
            'parameters': params,
            'conditions': task['conditions'] or '',
            'answer_type': task['answer_type'] or 'numeric'
        }

        variant = TaskGenerator.generate_task_variant(template_dict, band=None)

        # --- Сохраняем как retry-вариант ---
        cursor.execute('''
            INSERT INTO student_task_variants
            (lesson_id, user_id, task_id, variant_data, variant_type)
            VALUES (%s, %s, %s, %s, 'retry')
            ON CONFLICT (lesson_id, user_id, task_id, variant_type)
            DO UPDATE SET variant_data = EXCLUDED.variant_data
        ''', (task['lesson_id'], user_id, task_id, json.dumps(variant)))

        conn.commit()
        return jsonify(variant)

    except Exception as e:
        print(f"ERROR generating retry task: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()



if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)