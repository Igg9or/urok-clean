document.addEventListener('DOMContentLoaded', function() {
    const lessonId = window.location.pathname.split('/').pop();
    const tasksContainer = document.getElementById('tasksContainer');
    const addTaskBtn = document.getElementById('addTaskBtn');
    const saveLessonBtn = document.getElementById('saveLessonBtn');
    const textbookSelect = document.getElementById('textbookSelect');
    const templateSearch = document.getElementById('templateSearch');
    const templatesList = document.getElementById('templatesList');
    const taskIndexList = document.getElementById('taskIndexList');
const taskIndexCount = document.getElementById('taskIndexCount');


    // Кэш для хранения загруженных шаблонов
    const templatesCache = {};

    // Загрузка шаблонов из учебника
    textbookSelect.addEventListener('change', loadTemplates);
    templateSearch.addEventListener('input', filterTemplates);

    // Добавление задания из шаблона
    templatesList.addEventListener('click', function(e) {
        if (e.target.classList.contains('btn-use-template')) {
            const templateId = e.target.dataset.templateId;
            addTaskFromTemplate(templateId);
        }
    });

    // Загрузка шаблонов
    function loadTemplates() {
        const textbookId = textbookSelect.value;
        if (!textbookId) {
            templatesList.innerHTML = '<div class="empty-state"><p>Выберите учебник для просмотра заданий</p></div>';
            return;
        }

        fetch(`/api/textbooks/${textbookId}/templates`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    renderTemplates(data.templates);
                }
            });
    }

    // Фильтрация шаблонов
    function filterTemplates() {
        const searchTerm = templateSearch.value.toLowerCase();
        const items = templatesList.querySelectorAll('.template-item');
        
        items.forEach(item => {
            const text = item.textContent.toLowerCase();
            item.style.display = text.includes(searchTerm) ? 'block' : 'none';
        });
    }


        // где-нибудь выше renderTemplates
function naturalKey(str) {
  const CYR = " абвгдеёжзийклмнопрстуфхцчшщъыьэюя";
  const idx = ch => {
    const i = CYR.indexOf(ch);
    return i === -1 ? 999 : i;
  };
  const parts = String(str || "").toLowerCase().match(/\d+|[a-zа-яё]+/g) || [];
  return parts.map(p => (/^\d+$/.test(p) ? [0, parseInt(p,10)] : [1, ...[...p].map(idx)]));
}

function sortNaturally(arr) {
  return [...arr].sort((a, b) => {
    const A = naturalKey(a.name), B = naturalKey(b.name);
    const n = Math.max(A.length, B.length);
    for (let i=0; i<n; i++) {
      const pa = A[i] || [0, -1], pb = B[i] || [0, -1];
      const m = Math.max(pa.length, pb.length);
      for (let j=0; j<m; j++) {
        const va = pa[j] ?? -1, vb = pb[j] ?? -1;
        if (va !== vb) return va < vb ? -1 : 1;
      }
    }
    return 0;
  });
}


function renderTaskIndex() {
  if (!taskIndexList) return;

  const cards = Array.from(document.querySelectorAll('.task-card'));
  taskIndexList.innerHTML = '';

  cards.forEach((card, idx) => {
    const number = idx + 1;

    const templateName = (card.dataset.templateName || '').trim();
let teaser = templateName;

// запасной вариант — если имени нет (пустое задание), показываем кусок вопроса
if (!teaser) {
  const questionEl = card.querySelector('.task-question');
  const questionText = (questionEl?.value || questionEl?.textContent || '').trim();
  teaser = questionText ? questionText.replace(/\s+/g, ' ').slice(0, 40) : '';
}

    const li = document.createElement('li');
    li.dataset.index = idx;
    li.innerHTML = `
      <span class="label"><i class="icon-hash"></i> № ${number}</span>
      <span class="meta">${teaser}</span>
    `;
    li.addEventListener('click', () => {
      cards.forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      card.scrollIntoView({ behavior: 'smooth', block: 'start' });

      taskIndexList.querySelectorAll('li').forEach(n => n.classList.remove('active'));
      li.classList.add('active');

      setTimeout(() => card.classList.remove('active'), 800);
    });

    taskIndexList.appendChild(li);
  });

  if (taskIndexCount) taskIndexCount.textContent = String(cards.length);
}



    // Отображение шаблонов
    function renderTemplates(templates) {
        if (templates.length === 0) {
            templatesList.innerHTML = '<div class="empty-state"><p>В этом учебнике нет шаблонов заданий</p></div>';
            return;
        }
        
        templatesList.innerHTML = templates.map(template => `
            <div class="template-item">
                <h4>${template.name}</h4>
                <p>${template.question_template}</p>
                <div class="template-actions">
                    <button class="btn btn-small btn-use-template" data-template-id="${template.id}">
                        Добавить в урок
                    </button>
                </div>
            </div>
        `).join('');
    }

    // Добавление задания из шаблона
    function addTaskFromTemplate(templateId) {
        // Проверяем кэш
        if (templatesCache[templateId]) {
            processTemplate(templatesCache[templateId]);
            return;
        }
        
        fetch(`/api/templates/${templateId}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    templatesCache[templateId] = data.template;
                    processTemplate(data.template);
                }
            });
    }

    function processTemplate(template) {
  addTask(template.question_template, template.answer_template);

  const taskCard = tasksContainer.lastElementChild;
  taskCard.dataset.templateId = template.id;
  taskCard.dataset.templateName = template.name;   // <-- ДОБАВИЛИ

  // Генерируем пример для ученика сразу после добавления
  generateStudentPreview(taskCard);
}

    function generateStudentPreview(taskCard) {
    const templateId = taskCard.dataset.templateId;
    if (!templateId) return;

    // Делаем AJAX-запрос к backend
    fetch(`/api/generate_from_template/${templateId}`)
        .then(response => response.json())
        .then(variant => {
            // Пример для ученика:
            const previewQuestion = taskCard.querySelector('.student-preview-question');
            const previewAnswer = taskCard.querySelector('.student-preview-answer');

            if (variant && previewQuestion && previewAnswer) {
                previewQuestion.textContent = variant.question;
                previewAnswer.textContent = variant.correct_answer;
            } else {
                if (previewQuestion) previewQuestion.textContent = "Ошибка генерации";
                if (previewAnswer) previewAnswer.textContent = "Ошибка генерации";
            }
        })
        .catch(e => {
            const previewQuestion = taskCard.querySelector('.student-preview-question');
            const previewAnswer = taskCard.querySelector('.student-preview-answer');
            if (previewQuestion) previewQuestion.textContent = "Ошибка связи с сервером";
            if (previewAnswer) previewAnswer.textContent = "Ошибка связи с сервером";
        });
}


// Вспомогательная функция для генерации случайных чисел
function randomInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}

    function formatConstraintType(type) {
        const types = {
            'multiple_of': 'Кратно',
            'greater_than': 'Больше чем',
            'less_than': 'Меньше чем',
            'equals': 'Равно'
        };
        return types[type] || type;
    }

    // Генерация примера для учителя
    function generateExample(questionTemplate, answerTemplate, taskCard) {
        const paramRegex = /\{([A-Za-z]+)\}/g;
        let params = {};
        let match;
        
        // Находим все параметры в шаблоне
        const allParams = new Set();
        while ((match = paramRegex.exec(questionTemplate + answerTemplate))) {
            allParams.add(match[1]);
        }
        
        // Проверяем, есть ли сохраненные параметры из шаблона
        let templateParams = null;
        let conditions = '';
        if (taskCard.dataset.templateId && templatesCache[taskCard.dataset.templateId]) {
            try {
                templateParams = JSON.parse(templatesCache[taskCard.dataset.templateId].parameters);
                conditions = templateParams.conditions || '';
            } catch (e) {
                console.error('Error parsing template params:', e);
            }
        }
        
        // Генерируем значения с учетом ограничений и условий
        let attempts = 0;
        const maxAttempts = 100; // Максимальное количество попыток
        
        generateParams: while (attempts < maxAttempts) {
            attempts++;
            params = {}; // Сбрасываем параметры перед каждой попыткой
            
            for (const param of allParams) {
                if (templateParams && templateParams[param]) {
                    // Используем параметры из шаблона
                    const config = templateParams[param];
                    let value;
                    
                    if (config.type === 'int') {
                        value = randomInt(config.min, config.max);
                        
                        // Применяем ограничения
                        if (config.constraints) {
                            for (const constraint of config.constraints) {
                                if (constraint.type === 'multiple_of') {
                                    const remainder = value % constraint.value;
                                    if (remainder !== 0) {
                                        value += (constraint.value - remainder);
                                        if (value > config.max) {
                                            value -= constraint.value;
                                        }
                                    }
                                }
                            }
                        }
                    } else {
                        value = randomInt(config.min, config.max);
                    }
                    
                    params[param] = value;
                } else {
                    // Генерируем случайное значение, если нет шаблона
                    params[param] = randomInt(1, 10);
                }
            }
            
            // Проверяем условия, если они есть
            if (conditions) {
                try {
                    // Заменяем {param} на params.param в условиях
                    let evalConditions = conditions;
                    for (const param in params) {
                        evalConditions = evalConditions.replace(
                            new RegExp(`\\{${param}\\}`, 'g'), 
                            params[param]
                        );
                    }
                    
                    // Выполняем проверку условий
                    if (!eval(evalConditions)) {
                        continue generateParams; // Условия не выполнены - пробуем снова
                    }
                } catch (e) {
                    console.error('Error evaluating conditions:', e);
                    // Если не удалось проверить условия, продолжаем
                    break;
                }
            }
            
            // Если дошли сюда - условия выполнены или их нет
            break;
        }
        
        // Заменяем параметры в вопросе
        let exampleQuestion = questionTemplate;
        for (const [param, value] of Object.entries(params)) {
            exampleQuestion = exampleQuestion.replace(new RegExp(`\\{${param}\\}`, 'g'), value);
        }
        
        // Вычисляем ответ
        let exampleAnswer;
        try {
            let answerFormula = answerTemplate;
            for (const [param, value] of Object.entries(params)) {
                answerFormula = answerFormula.replace(new RegExp(`\\{${param}\\}`, 'g'), value);
            }
            exampleAnswer = safeEval(answerFormula)?.toString() ?? "Ошибка в формуле";
        } catch (e) {
            exampleAnswer = "Ошибка в формуле ответа";
        }
        
        return {
            question: exampleQuestion,
            answer: exampleAnswer,
            params: params
        };
    }

    function randomInt(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    // Безопасное вычисление выражения
    function safeEval(formula) {
        // Удаляем все потенциально опасные символы
        const cleanFormula = formula.replace(/[^0-9+\-*/().{}\s]/g, '');
        try {
            return new Function('return ' + cleanFormula)();
        } catch (e) {
            console.error('Ошибка вычисления:', e);
            return null;
        }
    }

    // Обновление предпросмотра
    function updatePreview(taskCard) {
        const question = taskCard.querySelector('.task-question').value;
        const answer = taskCard.querySelector('.task-answer').value;
        const preview = taskCard.querySelector('.teacher-preview');
        
        if (!question || !answer) {
            preview.classList.add('hidden');
            return;
        }
        
        const example = generateExample(question, answer, taskCard);
        
        taskCard.querySelector('.preview-question').textContent = example.question;
        taskCard.querySelector('.preview-answer').textContent = example.answer;
        taskCard.querySelector('.preview-params').textContent = 
            Object.entries(example.params).map(([k, v]) => `${k}=${v}`).join(', ');
        
        preview.classList.remove('hidden');
    }

    // Добавление нового задания
    function addTask(question = '', answer = '') {
    const taskNumber = tasksContainer.children.length + 1;
    const taskCard = document.createElement('div');
    taskCard.className = 'task-card';
    taskCard.innerHTML = `
        <div class="task-header">
            <h3>Задание <span class="task-number">${taskNumber}</span></h3>
            <button class="btn btn-danger btn-remove-task">Удалить</button>
        </div>
        <textarea class="task-question">${question}</textarea>
        <div class="answer-section">
            <label>Формула ответа:</label>
            <textarea class="task-answer">${answer}</textarea>
        </div>
        
        <!-- Добавленный блок для предпросмотра ученика -->
        <div class="student-preview">
            <h4>Пример для ученика:</h4>
            <div class="preview-content">
                <p><strong>Задание:</strong> <span class="student-preview-question"></span></p>
                <p><strong>Правильный ответ:</strong> <span class="student-preview-answer"></span></p>
            </div>
        </div>
        
        <div class="teacher-preview hidden">
            <h4>Пример для учителя:</h4>
            <div class="preview-content">
                <p><strong>Пример задания:</strong> <span class="preview-question"></span></p>
                <p><strong>Правильный ответ:</strong> <span class="preview-answer"></span></p>
                <p><strong>Используемые параметры:</strong> <span class="preview-params"></span></p>
            </div>
            <button class="btn btn-small btn-generate-preview">Сгенерировать новый пример</button>
        </div>
        <button class="btn btn-small btn-show-preview">Показать пример</button>
    `;
    tasksContainer.appendChild(taskCard);
    updateTaskNumbers();
    
    // Если добавляем из шаблона, сразу показываем пример для ученика
    if (question && answer) {
        generateStudentPreview(taskCard);
    }
}

    // Обновление нумерации заданий
    function updateTaskNumbers() {
        document.querySelectorAll('.task-card').forEach((card, index) => {
            card.querySelector('.task-number').textContent = index + 1;
        });
        renderTaskIndex();

    }

    // Обработчики событий
    document.addEventListener('click', function(e) {
        // Показать/скрыть превью
        if (e.target.classList.contains('btn-show-preview')) {
            const taskCard = e.target.closest('.task-card');
            const preview = taskCard.querySelector('.teacher-preview');
            const isHidden = preview.classList.contains('hidden');
            
            if (isHidden) {
                updatePreview(taskCard);
                e.target.textContent = 'Скрыть пример';
            } else {
                preview.classList.add('hidden');
                e.target.textContent = 'Показать пример';
            }
        }
        
        // Сгенерировать новый пример
        if (e.target.classList.contains('btn-generate-preview')) {
            const taskCard = e.target.closest('.task-card');
            updatePreview(taskCard);
        }
    });


    tasksContainer.addEventListener('input', function(e) {
  if (e.target.classList.contains('task-question')) {
    renderTaskIndex();
  }
});


    // Удаление задания
    tasksContainer.addEventListener('click', function(e) {
        if (e.target.classList.contains('btn-remove-task')) {
            const taskCard = e.target.closest('.task-card');
            const taskId = taskCard.dataset.taskId;
            
            if (taskId) {
                fetch(`/teacher/delete_task/${taskId}`, {
                    method: 'DELETE'
                }).then(response => {
                    if (response.ok) {
                        taskCard.remove();
                        updateTaskNumbers();
                    }
                });
            } else {
                taskCard.remove();
                updateTaskNumbers();
            }
        }
    });

    // Сохранение урока
    saveLessonBtn.addEventListener('click', function() {
        const tasks = [];
        document.querySelectorAll('.task-card').forEach(taskCard => {
            tasks.push({
                id: taskCard.dataset.taskId || null,
                question: taskCard.querySelector('.task-question').value,
                answer: taskCard.querySelector('.task-answer').value,
                template_id: taskCard.dataset.templateId || null  // Добавляем template_id
            });
        });

        fetch(`/teacher/update_lesson/${lessonId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ tasks: tasks })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('Изменения сохранены!');
                // Обновляем ID новых заданий
                data.tasks.forEach((task, index) => {
                    if (!tasks[index].id) {
                        document.querySelectorAll('.task-card')[index].dataset.taskId = task.id;
                    }
                });
            }
        });
    });

    // Добавление пустого задания
    addTaskBtn.addEventListener('click', function() {
        addTask();
        updateTaskNumbers();

    });
    renderTaskIndex();

});