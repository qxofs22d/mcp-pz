## Модуль: Менеджер проекта

### 1. Спецификация ТЗ

**Название и место в архитектуре**  
Менеджер проекта — MCP-сервер, отвечающий за создание, открытие и сохранение проекта, управление файловой структурой, состоянием и доступом к файлам.

**Цель (зачем нужен)**  
- Обеспечить единую точку управления проектом: создание папок, копирование PDF, сохранение прогресса.  
- Хранить состояние проекта (загруженные PDF, структуру разделов, ссылки на сгенерированные тексты) в `state.json`.  
- Предоставлять другим модулям (через MCP) доступ к путям и метаданным.

**Входные данные**  
Команды от ИИ-ассистента (оркестратора) через MCP:
- `create_project(path)` — создать новый проект в указанной папке.
- `load_project(path)` — загрузить существующий проект.
- `add_pdf(file_path)` — добавить PDF в проект (копирует в `pdf/`).
- `get_state()` — получить текущее состояние.
- `update_state(updates)` — обновить отдельные поля состояния.
- `save_state()` — принудительное сохранение.
- `save_section_text(section_title, text)` — сохранить текст раздела в `output/` и обновить состояние.

**Выходные данные**  
- Статус операции или объект состояния (JSON).

**Основная логика (псевдокод)**
class ProjectManager:
    def __init__(self, project_path):
        self.path = project_path
        self.state = self._load_state()
    
    def create_project(self, path):
        create_directories(path/'pdf', path/'data', path/'output')
        self.state = default_state
        self._save_state()
    
    def add_pdf(self, file_path):
        dest = self.path/'pdf'/os.path.basename(file_path)
        shutil.copy(file_path, dest)
        self.state['pdfs'].append({
            'filename': os.path.basename(file_path),
            'relative_path': str(dest.relative_to(self.path)),
            'processed': False,
            'indexed': False
        })
        self._save_state()
    
    def save_section_text(self, title, text):
        filename = f"{title.lower().replace(' ', '_')}.md"
        filepath = self.path/'output'/filename
        with open(filepath, 'w') as f:
            f.write(text)
        # обновить состояние
        for sec in self.state['sections']:
            if sec['title'] == title:
                sec['output_file'] = str(filepath.relative_to(self.path))
                sec['status'] = 'draft'
                break
        self._save_state()
	
**Обработка ошибок**  
- При отсутствии папки проекта или файла состояния — возвращать ошибку с предложением создать новый проект.
- При ошибках копирования файла — возвращать детальное сообщение.

**Нефункциональные требования**  
- Автосохранение после каждого изменения.
- Корректная обработка путей (относительные/абсолютные).

### 2. Стратегия реализации

**Исполнитель**  
Реализуется как отдельный MCP-сервер на Python, запускаемый оркестратором как дочерний процесс.

**Критерии успеха**  
- Все инструменты работают согласно спецификации.
- Состояние сохраняется и восстанавливается.
- Проектная структура создаётся корректно.

### 3. Критерии приемки
- [ ] Создание проекта с папками pdf, data, output и файлом state.json.
- [ ] Добавление PDF копирует файл и обновляет state.
- [ ] Загрузка проекта восстанавливает состояние.
- [ ] Сохранение текста раздела создаёт файл и обновляет state.

---
