# Stratton Internship Bot

## Архитектура

```
stratton_bot/
├── bot.py                  # Точка входа, DI, планировщик
├── settings.py             # Pydantic Settings (конфигурация)
├── texts.py                # Все текстовые константы
├── database/
│   ├── models.py           # SQLAlchemy модели
│   └── session.py          # Менеджер сессий (context manager)
├── dto/                    # Data Transfer Objects (dataclasses)
├── repositories/           # Слой доступа к данным (SQL)
├── services/               # Бизнес-логика
├── infrastructure/                  # Внешние сервисы (Gemini OCR)
├── handlers/               # Обработчики (только ввод/вывод)
├── keyboards/              # Клавиатуры
└── static/                 # Статика (NDA шаблон)
```

