"""
Background task: fetch classroom assignments, save via service, persist next_run in DB.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from dashboard.core.task import (
    BaseTask,
    TaskType,
    update_after_run,
)
from dashboard.plugins.classroom.service import save_assignments


class ClassroomTask(BaseTask):
    """Fetch assignments from API/scraper, save to DB, update next_run."""

    def __init__(self, component_name: str, config: Dict[str, Any]):
        schedule_type, schedule_config = self._schedule_from_config(config)
        super().__init__(component_name, schedule_type, schedule_config)
        self.config = config

    def _schedule_from_config(self, config: Dict[str, Any]) -> tuple:
        update_interval = config.get("update_interval", 3600)
        sec = update_interval if update_interval < 100000 else update_interval // 1000
        return TaskType.INTERVAL_SECONDS, {"interval_seconds": sec}

    def run(
        self,
        config: Dict[str, Any],
        result_queue: Any,
        config_data: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        fetchers = self._build_fetchers(config)
        if not fetchers:
            try:
                result_queue.put((self.component_name, []))
            except Exception:
                pass
            return
        all_assignments: List[Dict[str, Any]] = []
        errors: List[str] = []
        for fetcher in fetchers:
            try:
                self.logger.info(f"Classroom Homework: fetching for {fetcher.student_name}")
                assignments = fetcher.get_due_assignments(
                    include_overdue=True,
                    fetch_submission_status=True,
                )
                all_assignments.extend(assignments)
            except Exception as e:
                self.logger.exception(f"Fetch failed for {fetcher.student_name}")
                errors.append(f"{fetcher.student_name}: {e}")
        if errors:
            self.logger.warning(f"Classroom fetch errors: {errors}")
        all_assignments.sort(key=lambda a: a.get("due_datetime") or datetime.max)
        save_assignments(self.component_name, all_assignments)
        self.logger.info(f"Classroom Homework: saved {len(all_assignments)} assignment(s) to DB")
        update_after_run(self.component_name)
        try:
            result_queue.put((self.component_name, all_assignments))
        except Exception:
            pass

    def _build_fetchers(self, config: Dict[str, Any]) -> List[Any]:
        class _FetcherBuilder:
            def __init__(self, cfg, logger):
                self.config = cfg
                self.logger = logger
            def _get_client_secret_path(self):
                import os
                path = self.config.get("client_secret_path") or os.environ.get(
                    "GOOGLE_CLASSROOM_CLIENT_SECRET", ""
                )
                if path:
                    path = os.path.expanduser(os.path.expandvars(path))
                return path
            def _build_fetchers(self):
                import os
                from .classroom_client import ClassroomClient
                from .classroom_scraper import ClassroomScraper
                fetchers = []
                backend = (self.config.get("backend") or "api").lower()
                students = self.config.get("students") or []
                if backend == "scrape":
                    for entry in students:
                        name = entry.get("name")
                        profile_path = entry.get("profile_path")
                        if not name or not profile_path:
                            continue
                        profile_path = os.path.expanduser(os.path.expandvars(profile_path))
                        fetchers.append(
                            ClassroomScraper(
                                student_name=name,
                                profile_path=profile_path,
                                logger=self.logger,
                            )
                        )
                    return fetchers
                client_secret = self._get_client_secret_path()
                for entry in students:
                    name = entry.get("name")
                    token_file = entry.get("token_file")
                    if not name or not token_file:
                        continue
                    token_file = os.path.expanduser(os.path.expandvars(token_file))
                    fetchers.append(
                        ClassroomClient(
                            student_name=name,
                            client_secret_path=client_secret,
                            token_path=token_file,
                            logger=self.logger,
                        )
                    )
                return fetchers
        builder = _FetcherBuilder(config, self.logger)
        return builder._build_fetchers()
