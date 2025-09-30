console.log('student_lesson.js v5 loaded');

// Глобальные переменные для модального окна перерешивания
let currentRetryTaskCard = null;
let currentRetryTaskId = null;

document.addEventListener('DOMContentLoaded', function() {
    // Загружаем сохраненные ответы при старте
    loadSavedAnswers();

    // Вешаем обработчики на все кнопки проверки
    document.querySelectorAll('.btn-check').forEach(button => {
        button.addEventListener('click', function() {
            checkAnswer(this.closest('.task-card'));
        });
    });

    initRetryModal();

    function extractQuestionForAI(taskCard) {
        const qNode = taskCard.querySelector('.task-question');
        if (!qNode) return '';

        // 1) Пытаемся взять сырой HTML/LaTeX из data-атрибута
        let raw = qNode.dataset ? qNode.dataset.questionRaw : '';
        if (raw) {
            try { raw = JSON.parse(raw); } catch { /* уже строка */ }
        } else {
            // 2) Фоллбэк — берём HTML, а не textContent (так не потеряем дроби/степени)
            raw = qNode.innerHTML || '';
        }

        // Лёгкая нормализация (чтобы модель видела операции):
        raw = raw
            .replace(/<br\s*\/?>/gi, '\n')
            .replace(/<sup>(.*?)<\/sup>/gi, '^$1')
            .replace(/&times;|×/g, '\\cdot')
            .replace(/&divide;|÷/g, '\\div');

        return raw.trim();
        }


    
            // Функция для показа кнопки "Решить еще раз"
    function showRetryButton(taskCard) {
        const retryButton = taskCard.querySelector('.btn-retry');
        if (retryButton) {
            retryButton.classList.remove('hidden');
            
            // Обработчик для кнопки "Решить еще раз"
            retryButton.onclick = () => openRetryModal(taskCard);
        }
    }

    // Функция открытия модального окна
    async function openRetryModal(taskCard) {
        currentRetryTaskCard = taskCard;
        currentRetryTaskId = taskCard.dataset.taskId;
        
        const modal = document.getElementById('retryModal');
        const content = modal.querySelector('.retry-task-content');
        
        // Показываем загрузку
        content.innerHTML = '<div class="loading">Загрузка нового задания...</div>';
        modal.classList.remove('hidden');
        
        try {
            // Загружаем новое задание
            await loadNewTaskVariant(taskCard, content);
        } catch (error) {
            console.error('Ошибка загрузки нового задания:', error);
            content.innerHTML = '<div class="error">Ошибка загрузки задания</div>';
        }
    }

    // Функция загрузки нового варианта задания
    async function loadNewTaskVariant(taskCard, contentContainer) {
        const taskId = taskCard.dataset.taskId;
        const userId = taskCard.dataset.userId;
        
        console.log('Загрузка нового задания для taskId:', taskId);
        
        if (!taskId) {
            contentContainer.innerHTML = '<div class="error">Ошибка: не найден ID задания</div>';
            return;
        }
        
        try {
            const response = await fetch(`/api/generate_retry_task/${taskId}`);
            console.log('Response status:', response.status);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const newTask = await response.json();
            console.log('Получено новое задание:', newTask);
            
            if (newTask.error) {
                throw new Error(newTask.error);
            }
            
            // Нормализуем LaTeX в вопросе
            const normalizedQuestion = normalizeLatexForRetry(newTask.question);
            
            // Отображаем новое задание с правильным форматированием LaTeX
            contentContainer.innerHTML = `
                <div class="retry-task">
                    <div class="task-question" id="retry-question">${normalizedQuestion || 'Вопрос не сгенерирован'}</div>
                    <div class="task-answer">
                        <input type="text" class="retry-answer-input" placeholder="Введите ваш ответ">
                    </div>
                    <div class="retry-feedback hidden"></div>
                    <input type="hidden" class="retry-correct-answer" value="${newTask.correct_answer || ''}">
                    <input type="hidden" class="retry-answer-type" value="${taskCard.dataset.answerType || 'numeric'}">
                </div>
            `;
            
            // Применяем MathJax к новому контенту
            if (window.MathJax && typeof MathJax.typesetPromise === 'function') {
                try {
                    await MathJax.typesetPromise([contentContainer]);
                    console.log('MathJax applied to retry task');
                } catch (mathError) {
                    console.error('MathJax error:', mathError);
                }
            }
            
            // Добавляем обработчик для кнопки проверки в модалке
            document.querySelector('.btn-check-retry').onclick = checkRetryAnswer;
            
        } catch (error) {
            console.error('Ошибка загрузки нового задания:', error);
            contentContainer.innerHTML = `
                <div class="error">
                    Ошибка загрузки задания: ${error.message}
                    <br>Task ID: ${taskId}
                </div>
            `;
        }
    }

    // Функция для нормализации LaTeX в модальном окне
function normalizeLatexForRetry(text) {
    if (!text) return text;
    
    let normalized = String(text);
    
    // Заменяем неправильные escape-последовательности
    normalized = normalized.replace(/\\\\\(/g, '\\(').replace(/\\\\\)/g, '\\)');
    normalized = normalized.replace(/\\\\\[/g, '\\[').replace(/\\\\\]/g, '\\]');
    
    // Исправляем распространенные проблемы с LaTeX
    normalized = normalized.replace(/\\cdot/g, '\\cdot ');
    normalized = normalized.replace(/\\times/g, '\\times ');
    
    return normalized;
}

    // Функция проверки ответа в модальном окне
    async function checkRetryAnswer() {
        const modal = document.getElementById('retryModal');
        const input = modal.querySelector('.retry-answer-input');
        const feedback = modal.querySelector('.retry-feedback');
        const correctAnswer = modal.querySelector('.retry-correct-answer').value;
        const answerType = modal.querySelector('.retry-answer-type').value;
        const userAnswer = input.value.trim();
        
        if (!userAnswer) {
            alert('Введите ответ!');
            return;
        }
        
        try {
            const response = await fetch('/api/check_answer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    answer: userAnswer,
                    correct_answer: correctAnswer,
                    answer_type: answerType
                })
            });
            
            const result = await response.json();
            
            if (result.is_correct) {
                // Если правильно - засчитываем оригинальное задание как верное
                feedback.innerHTML = '<div class="success">Правильно! Задание засчитано.</div>';
                feedback.classList.remove('hidden');
                
                // Блокируем поле ввода
                input.disabled = true;
                document.querySelector('.btn-check-retry').disabled = true;
                
                // Сохраняем результат для оригинального задания
                setTimeout(async () => {
                    await saveAnswerToServer(currentRetryTaskId, userAnswer, true);
                    
                    // Обновляем интерфейс оригинального задания
                    showResult(currentRetryTaskCard, true, userAnswer);
                    currentRetryTaskCard.querySelector('.answer-input').disabled = true;
                    currentRetryTaskCard.querySelector('.btn-check').disabled = true;
                    currentRetryTaskCard.querySelector('.btn-retry').classList.add('hidden');
                    
                    // Закрываем модальное окно
                    closeRetryModal();
                }, 1500);
                
            } else {
                // Если неправильно - показываем ошибку
                feedback.innerHTML = `
                    <div class="error">
                        Неправильно! Правильный ответ: ${correctAnswer}
                        <br>Больше нельзя перерешать это задание.
                    </div>
                `;
                feedback.classList.remove('hidden');
                
                // Блокируем дальнейшие попытки
                input.disabled = true;
                document.querySelector('.btn-check-retry').disabled = true;
                document.querySelector('.btn-cancel').textContent = 'Закрыть';
                
                // Сохраняем результат как неправильный
                await saveAnswerToServer(currentRetryTaskId, userAnswer, false);
            }
            
        } catch (error) {
            console.error('Ошибка проверки:', error);
            feedback.innerHTML = '<div class="error">Ошибка проверки ответа</div>';
            feedback.classList.remove('hidden');
        }
    }

    // Функция закрытия модального окна
    function closeRetryModal() {
        const modal = document.getElementById('retryModal');
        modal.classList.add('hidden');
        currentRetryTaskCard = null;
        currentRetryTaskId = null;
    }

    // Инициализация модального окна
    function initRetryModal() {
        const modal = document.getElementById('retryModal');
        
        // Закрытие по кнопке X
        modal.querySelector('.btn-close').onclick = closeRetryModal;
        
        // Закрытие по кнопке Отмена
        modal.querySelector('.btn-cancel').onclick = closeRetryModal;
        
        // Закрытие по клику вне модального окна
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeRetryModal();
            }
        });
    }
    
    // Функция загрузки сохраненных ответов
    async function loadSavedAnswers() {
        const lessonId = window.location.pathname.split('/').pop();
        const firstCard = document.querySelector('.task-card');
        if (!firstCard) return;
        const userId = firstCard.dataset.userId;

        try {
            const response = await fetch(`/get_student_answers/${lessonId}/${userId}`);
            const answers = await response.json();

            answers.forEach(answer => {
                const taskCard = document.querySelector(`.task-card[data-task-id="${answer.task_id}"]`);
                if (taskCard) {
                    const input = taskCard.querySelector('.answer-input');
                    const button = taskCard.querySelector('.btn-check');

                    // Восстанавливаем сохраненный ответ
                    if (answer.answer) {
                        input.value = answer.answer;
                    }

                    // Если ответ уже проверен - блокируем и показываем результат
                    if (answer.is_correct !== null) {
                        input.disabled = true;
                        button.disabled = true;
                        showResult(taskCard, answer.is_correct, answer.answer);
                    }
                }
            });
        } catch (error) {
            console.error('Ошибка загрузки ответов:', error);
        }
    }

    // Функция проверки ответа (основная логика без изменений)
    async function checkAnswer(taskCard) {
        const taskId = taskCard.dataset.taskId;
        let userAnswer = taskCard.querySelector('.answer-input').value.trim();

// ✅ Автозамена "√5" → "sqrt(5)" перед отправкой
userAnswer = userAnswer.replace(/([0-9]*\.?[0-9]*|)\s*√\s*(\(?[a-zA-Z0-9+*/\s-]+\)?)/g, function(_, coeff, radicand) {
    const coefficient = coeff.trim() === '' ? '' : coeff.trim() + '*';
    return coefficient + 'sqrt(' + radicand.trim() + ')';
});
        const correctAnswer = taskCard.dataset.correctAnswer;
        const answerType = taskCard.dataset.answerType || 'numeric';

        // Счетчик попыток на карточке
        if (typeof taskCard.attempts === "undefined") taskCard.attempts = 0;

        // Проверяем, не отправлен ли уже ответ
        if (taskCard.querySelector('.answer-input').disabled) {
            return;
        }

        if (!userAnswer) {
            alert('Введите ответ!');
            return;
        }

        try {
            const response = await fetch('/api/check_answer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task_id: taskId,
                    answer: userAnswer,
                    correct_answer: correctAnswer,
                    answer_type: answerType
                })
            });

            const result = await response.json();

            if (result.error) {
                throw new Error(result.error);
            }

            taskCard.attempts += 1; // +1 попытка

            // Показываем результат
            showResult(taskCard, result.is_correct, userAnswer);

            if (result.is_correct) {
    // Если правильно — блокируем поле
    taskCard.querySelector('.answer-input').disabled = true;
    taskCard.querySelector('.btn-check').disabled = true;
    await saveAnswerToServer(taskId, userAnswer, true);

} else if (taskCard.attempts >= 2) {
    // Если 2 ошибки — блокируем, сохраняем и показываем правильный ответ
    taskCard.querySelector('.answer-input').disabled = true;
    taskCard.querySelector('.btn-check').disabled = true;
    await saveAnswerToServer(taskId, userAnswer, false);
    taskCard.querySelector('.btn-dispute')?.classList.remove('hidden');

} else {
    // Это первая ошибка — не блокируем, не сохраняем
    taskCard.attempts += 1;

    // Автоматическая проверка по символам
    const normalizedUser = userAnswer.trim().replace(/\s+/g, '').toLowerCase();
    const normalizedCorrect = correctAnswer.trim().replace(/\s+/g, '').toLowerCase();

    if (normalizedUser === normalizedCorrect) {
        console.log("Ответ символически совпадает — автоматически засчитан.");
        taskCard.querySelector('.answer-input').disabled = true;
        taskCard.querySelector('.btn-check').disabled = true;
        taskCard.querySelector('.task-feedback .feedback-correct').classList.remove('hidden');
        taskCard.querySelector('.task-feedback .feedback-incorrect').classList.add('hidden');
        taskCard.querySelector('.answer-input').classList.add('correct');
        await saveAnswerToServer(taskId, userAnswer, true);
        return;
    }

    // Если не совпадает — остаёмся на первой ошибке
    taskCard.querySelector('.task-feedback .feedback-incorrect').classList.remove('hidden');
    taskCard.querySelector('.task-feedback .feedback-correct').classList.add('hidden');
}

        } catch (error) {
            console.error('Error:', error);
            alert('Произошла ошибка: ' + error.message);
        }
    }

    // Функция показа результата
    function showResult(taskCard, isCorrect, userAnswer) {
        const feedback = taskCard.querySelector('.task-feedback');
        const correctFeedback = taskCard.querySelector('.feedback-correct');
        const incorrectFeedback = taskCard.querySelector('.feedback-incorrect');
        const status = taskCard.querySelector('.task-status');

        if (isCorrect) {
            correctFeedback.classList.remove('hidden');
            incorrectFeedback.classList.add('hidden');
            status.style.backgroundColor = 'var(--success-color)';
        } else {
            correctFeedback.classList.add('hidden');
            incorrectFeedback.classList.remove('hidden');
            status.style.backgroundColor = 'var(--error-color)';
            
            // Изменяем текст для первой/второй попытки
            if (taskCard.attempts === 1) {
                incorrectFeedback.querySelector('.error-message').innerHTML = "Ответ неверный. Попробуй еще раз!";
            } else {
                incorrectFeedback.querySelector('.error-message').innerHTML =
                    "Ответ неверный. Правильный ответ: <span class='correct-answer'>" +
                    taskCard.dataset.correctAnswer +
                    "</span>";
                
                // ПОКАЗЫВАЕМ КНОПКУ "РЕШИТЬ ЕЩЕ РАЗ" после второй ошибки
                showRetryButton(taskCard);
                
                fetchAISolution(taskCard);
            }
        }

        feedback.classList.remove('hidden');
        updateProgress();
    }

    // Функция сохранения ответа на сервере
    async function saveAnswerToServer(taskId, answer, isCorrect) {
        try {
            await fetch('/save_answer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task_id: taskId,
                    answer: answer,
                    is_correct: isCorrect
                })
            });
        } catch (error) {
            console.error('Ошибка сохранения:', error);
        }
    }

    // Функция обновления прогресса (без изменений)
    function updateProgress() {
        const completedTasks = document.querySelectorAll('.task-status[style*="var(--success-color)"]').length;
        const totalTasks = document.querySelectorAll('.task-card').length;
        const percentage = Math.round((completedTasks / totalTasks) * 100);

        document.querySelector('.progress-fill').style.width = `${percentage}%`;
        document.querySelector('.progress-text').textContent =
            `${completedTasks} из ${totalTasks} заданий`;
    }

    let aiStepHistory = [];

    async function startAIStepDialog(taskCard) {
        const aiDialog = taskCard.querySelector('.ai-step-dialog');
        aiDialog.classList.remove('hidden');
        aiDialog.scrollIntoView({ behavior: "smooth", block: "center" });

        const questionText = extractQuestionForAI(taskCard);
        aiStepHistory = [];
        await fetchAndShowAIStep(taskCard, questionText, aiStepHistory);
        aiDialog.querySelector('.btn-exit-ai').onclick = () => aiDialog.classList.add('hidden');
        }


    async function fetchAndShowAIStep(taskCard, questionText, history) {
        const aiDialog = taskCard.querySelector('.ai-step-dialog');
        const userId = taskCard.dataset.userId; // <--- Вот это обязательно!
        aiDialog.querySelector('.ai-step-feedback').textContent = 'Загрузка шага...';

        try {
            const resp = await fetch('/api/ai_step_dialog', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    question: questionText,
                    history: history,
                    user_id: userId // теперь переменная определена!
                })
            });
            const step = await resp.json();
            if (step.error) throw new Error(step.error);
            showAIStep(taskCard, step, questionText, history);
        } catch (e) {
            aiDialog.querySelector('.ai-step-feedback').textContent = "Ошибка ИИ: " + e.message;
        }
    }

    function showAIStep(taskCard, step, questionText, history) {
        const aiDialog = taskCard.querySelector('.ai-step-dialog');
        aiDialog.querySelector('.ai-step-question').textContent = step.question;
        aiDialog.querySelector('.ai-step-feedback').textContent = '';
        aiDialog.querySelector('.btn-exit-ai').classList.remove('hidden');
        const optionsContainer = aiDialog.querySelector('.ai-step-options');
        optionsContainer.innerHTML = '';

        if (!step.question && (!step.options || step.options.length === 0)) {
            aiDialog.classList.add('hidden');
            return;
        }

        step.options.forEach((opt, idx) => {
            const btn = document.createElement('button');
            btn.textContent = opt;
            btn.onclick = async () => {
                if (idx === step.correct_index) {
                    aiDialog.querySelector('.ai-step-feedback').innerHTML = `<span style="color: #05943b; font-weight:500;">Верно!</span> ${step.explanation}`;
                    // Добавляем шаг в историю
                    const newHistory = history.concat([{ step, user_choice: idx, correct: true }]);

                    // Спрашиваем следующий шаг у сервера:
                    setTimeout(async () => {
                        await fetchAndShowAIStep(taskCard, questionText, newHistory);
                    }, 900);
                } else {
                    aiDialog.querySelector('.ai-step-feedback').innerHTML = `<span style="color: #e31c1c; font-weight:500;">Не совсем!</span> ${step.explanation}`;
                    // Можно повторить тот же шаг, или подсветить ошибку, или запросить упрощённый вариант у бэка
                }
            };
            optionsContainer.appendChild(btn);
        });
    }

    // === НОВАЯ ВЕРСИЯ ===
    async function fetchAISolution(taskCard) {
  // Контейнер решения внутри карточки
  const feedbackBlock = taskCard.querySelector('.task-feedback') || taskCard;
  let solutionNode = feedbackBlock.querySelector('.ai-solution');
  if (!solutionNode) {
    solutionNode = document.createElement('div');
    solutionNode.className = 'ai-solution';
    feedbackBlock.appendChild(solutionNode);
  }
  solutionNode.innerHTML = '<div class="ai-solution-block">Готовлю решение…</div>';

  // Нормализация LaTeX:
  //  A) [ ... ] с LaTeX-командами -> \( ... \) или \[ ... \]
  //  B) [ 42.52 ] и т.п. «числовые» -> \( 42.52 \)
  const normalizeLatexBlocks = (input) => {
  if (!input) return input;

  let s = String(input);

  // 1) Защитим уже корректную математику \( ... \) и \[ ... \]
  const protectedBlocks = [];
  s = s.replace(/\\\(([\s\S]*?)\\\)|\\\[([\s\S]*?)\\\]/g, (m) => {
    const token = `__MJX_PROTECTED_${protectedBlocks.length}__`;
    protectedBlocks.push(m);   // сохраняем как есть
    return token;              // временный маркер
  });

  // 2) [ ... ] с «похожей на математику» начинкой → \( ... \) или \[ ... \]
  s = s.replace(/\[\s*([\s\S]{1,2000}?)\s*\]/g, (m, inner) => {
    const hasTeX =
      /\\(?:frac|sqrt|sum|int|cdot|times|div|le|ge|neq|approx|bar|overline|underline|vec|hat|pi|alpha|beta|gamma|ldots|mathrm|mathbb|begin|end|boxed)\b/.test(inner) ||
      /[{}^_]/.test(inner);
    const looksNumeric = /^[0-9\s.,+\-*/^=()\\]+$/.test(inner);
    if (!hasTeX && !looksNumeric) return m;

    const isMultilineOrLong = /\n/.test(inner) || inner.length > 80;
    return isMultilineOrLong ? `\[${inner}\]` : `\(${inner}\)`;
  });

  // 3) Оборачивание «голых» команд LaTeX в \( ... \) (вне защищенных кусков)
  const wrapInline = (text, pattern) => text.replace(pattern, (m) => `\\(${m}\\)`);

  // \frac{...}{...}, \sqrt{...}
  s = wrapInline(s, /\\frac\{[^}]+\}\{[^}]+\}/g);
  s = wrapInline(s, /\\sqrt\{[^}]+\}/g);

  // \times, \div, \cdot
  s = wrapInline(s, /\\times\b/g);
  s = wrapInline(s, /\\div\b/g);
  s = wrapInline(s, /\\cdot\b/g);

  // Простые степени типа 10^2 или (a+b)^3 (если не уже в \( \))
  s = s.replace(/(?<!\\\()(\b[\d()a-zA-Z]+)\s*\^\s*([\-+]?\d+)(?!\\\))/g,
                (m, base, exp) => `\\(${base}^{${exp}}\\)`);

  // 4) Вернуть защищённые куски
  s = s.replace(/__MJX_PROTECTED_(\d+)__/g, (_, i) => protectedBlocks[Number(i)]);
    s = s.replace(/\\\\\(/g, '\\(').replace(/\\\\\)/g, '\\)');
  return s;
};

  // Данные для бэка
  const taskId        = taskCard.dataset.taskId;
 const qNode = taskCard.querySelector('.task-question');
const questionText = extractQuestionForAI(taskCard);


  const correctAnswer = taskCard.dataset.correctAnswer || '';
  const userId        = taskCard.dataset.userId || '';

  try {
    const resp = await fetch('/api/ai_full_solution', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: taskId,
        question: questionText,
        correct_answer: correctAnswer,
        user_id: userId
      })
    });

    if (!resp.ok) {
      solutionNode.textContent = 'Ошибка при получении решения.';
      return;
    }

    const data = await resp.json();
    let raw = data && data.solution ? data.solution : 'Ошибка получения решения.';

    // Нормализация
    raw = normalizeLatexBlocks(raw);

    // Markdown → HTML
    const html = (window.marked && typeof marked.parse === 'function')
      ? marked.parse(raw)
      : raw.replace(/\n/g, '<br>');

    solutionNode.innerHTML = `
  <div class="ai-solution-block">
    <h4>Пошаговое решение</h4>
    ${html}
  </div>
`;

    // MathJax только в пределах решения
    if (window.MathJax && typeof MathJax.typesetPromise === 'function') {
      await MathJax.typesetPromise([solutionNode]);
    }
  } catch (e) {
    console.error('fetchAISolution error:', e);
    solutionNode.textContent = 'Ошибка при получении решения.';
  }
}

document.querySelectorAll('.btn-dispute').forEach(button => {
    button.addEventListener('click', async function () {
        const taskCard = this.closest('.task-card');
        const studentAnswer = taskCard.querySelector('.answer-input').value.trim();
        const correctAnswer = taskCard.dataset.correctAnswer;
        const taskId = taskCard.dataset.taskId;

        try {
            const resp = await fetch('/dispute_answer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task_id: taskId,
                    answer: studentAnswer,
                    correct_answer: correctAnswer
                })
            });

            const result = await resp.json();
            if (result.result === 'accepted') {
                alert("Ваш ответ засчитан как правильный!");
                // Принудительно отметить как правильный:
                showResult(taskCard, true, studentAnswer);
                taskCard.querySelector('.answer-input').disabled = true;
                taskCard.querySelector('.btn-check').disabled = true;
                taskCard.querySelector('.btn-dispute').classList.add('hidden');
            } else {
                alert("К сожалению, ответ действительно отличается.");
            }
        } catch (e) {
            alert("Ошибка при оспаривании: " + e.message);
        }
    });
});



});
