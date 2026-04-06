# Stratton Internship Bot

## Run

```bash
python -m stratton_bot
```

## New structure

```text
.
├── locales/
│   └── ru.json
├── static/
│   └── nda_template.docx
├── stratton_bot/
│   ├── __main__.py
│   ├── container.py
│   ├── main.py
│   ├── application/
│   │   ├── ports/
│   │   ├── services/
│   │   └── use_cases/
│   ├── domain/
│   ├── infrastructure/
│   │   ├── ai/
│   │   ├── config/
│   │   ├── db/
│   │   │   └── repositories/
│   │   ├── documents/
│   │   ├── i18n/
│   │   └── scheduler/
│   └── presentation/
│       ├── handlers/
│       ├── keyboards/
│       └── middlewares/
├── requirements.txt
└── .env
```
