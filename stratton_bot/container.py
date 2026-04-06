from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stratton_bot.application.services.task_catalog import TaskCatalog
from stratton_bot.application.use_cases.admin import AdminUseCase
from stratton_bot.application.use_cases.menu import MenuUseCase
from stratton_bot.application.use_cases.nda import NDAUseCase
from stratton_bot.application.use_cases.ocr import IdentityCardOCRUseCase
from stratton_bot.application.use_cases.scheduler import SchedulerUseCase
from stratton_bot.application.use_cases.submission import SubmissionUseCase
from stratton_bot.application.use_cases.testing import TestingUseCase
from stratton_bot.infrastructure.ai.gemini import GeminiAIClient
from stratton_bot.infrastructure.ai.parsers import JsonResponseParser
from stratton_bot.infrastructure.ai.prompts import DictPromptBuilder
from stratton_bot.infrastructure.config.settings import AppConfig
from stratton_bot.infrastructure.db.session import DatabaseGateway
from stratton_bot.infrastructure.db.uow import SqlAlchemyUnitOfWork
from stratton_bot.infrastructure.documents.nda_generator import NDADocumentGenerator
from stratton_bot.infrastructure.documents.user_csv_exporter import UserCsvExporter
from stratton_bot.infrastructure.i18n.translator import Translator


@dataclass(slots=True)
class AppContainer:
    config: AppConfig
    db: DatabaseGateway
    translator: Translator
    task_catalog: TaskCatalog
    menu_use_case: MenuUseCase
    testing_use_case: TestingUseCase
    submission_use_case: SubmissionUseCase
    admin_use_case: AdminUseCase
    nda_use_case: NDAUseCase
    scheduler_use_case: SchedulerUseCase

    @classmethod
    def build(cls, config: AppConfig) -> "AppContainer":
        config.data_dir.mkdir(parents=True, exist_ok=True)
        config.backup_dir.mkdir(parents=True, exist_ok=True)

        db = DatabaseGateway(config.database_url, config.data_dir)
        translator = Translator(config.locales_dir, config.default_locale)
        task_catalog = TaskCatalog()

        def uow_factory() -> SqlAlchemyUnitOfWork:
            return SqlAlchemyUnitOfWork(db.session_factory)

        ocr_use_case = IdentityCardOCRUseCase(
            ai_client=GeminiAIClient(config.gemini_api_key),
            prompt_builder=DictPromptBuilder(),
            response_parser=JsonResponseParser(),
        )

        return cls(
            config=config,
            db=db,
            translator=translator,
            task_catalog=task_catalog,
            menu_use_case=MenuUseCase(uow_factory=uow_factory, task_catalog=task_catalog),
            testing_use_case=TestingUseCase(uow_factory=uow_factory, task_catalog=task_catalog, config=config),
            submission_use_case=SubmissionUseCase(uow_factory=uow_factory),
            admin_use_case=AdminUseCase(
                uow_factory=uow_factory,
                exporter=UserCsvExporter(),
            ),
            nda_use_case=NDAUseCase(
                uow_factory=uow_factory,
                ocr_use_case=ocr_use_case,
                document_generator=NDADocumentGenerator(config.static_dir / "nda_template.docx"),
                data_dir=config.data_dir,
            ),
            scheduler_use_case=SchedulerUseCase(uow_factory=uow_factory, config=config, task_catalog=task_catalog),
        )
