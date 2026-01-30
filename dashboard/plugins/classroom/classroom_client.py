"""
Google Classroom API client for one student account.
Handles OAuth2, listing courses, and coursework with due dates.
"""
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, date
import logging

# Optional imports - component will handle missing deps
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    HAS_GOOGLE_DEPS = True
except ImportError:
    HAS_GOOGLE_DEPS = False

SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly",
]


def _expand_path(path_str: str) -> str:
    """Expand user and env vars in path."""
    s = os.path.expanduser(path_str)
    s = os.path.expandvars(s)
    return s


def _parse_due_date(due_date: Optional[Dict], due_time: Optional[Dict]) -> Optional[datetime]:
    """Convert Classroom dueDate/dueTime to datetime."""
    if not due_date:
        return None
    try:
        y = due_date.get("year")
        m = due_date.get("month")
        d = due_date.get("day")
        if y is None or m is None or d is None:
            return None
        dt = datetime(y, m, d)
        if due_time:
            h = due_time.get("hours")
            mi = due_time.get("minutes")
            if h is not None and mi is not None:
                dt = dt.replace(hour=h, minute=mi, second=0, microsecond=0)
        return dt
    except (TypeError, ValueError):
        return None


class ClassroomClient:
    """One student account: OAuth2 + list courses and coursework with due dates."""

    def __init__(
        self,
        student_name: str,
        client_secret_path: str,
        token_path: str,
        logger: Optional[logging.Logger] = None,
    ):
        self.student_name = student_name
        self.client_secret_path = _expand_path(client_secret_path)
        self.token_path = _expand_path(token_path)
        self.logger = logger or logging.getLogger(__name__)
        self._service = None
        self._creds = None

    def _ensure_credentials(self) -> bool:
        """Load or run OAuth2 and build service. Returns True if ready."""
        if not HAS_GOOGLE_DEPS:
            self.logger.error("Google API libraries not installed")
            return False

        creds = None
        token_path = Path(self.token_path)
        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            except Exception as e:
                self.logger.warning(f"Could not load token for {self.student_name}: {e}")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            if not creds:
                if not Path(self.client_secret_path).exists():
                    self.logger.error(
                        f"Client secret not found: {self.client_secret_path} for {self.student_name}"
                    )
                    return False
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.client_secret_path, SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    self.logger.error(f"OAuth flow failed for {self.student_name}: {e}")
                    return False

            token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(token_path, "w") as f:
                f.write(creds.to_json())

        self._creds = creds
        try:
            self._service = build("classroom", "v1", credentials=creds)
        except Exception as e:
            self.logger.error(f"Failed to build Classroom service for {self.student_name}: {e}")
            return False
        return True

    def get_due_assignments(
        self,
        include_overdue: bool = True,
        fetch_submission_status: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Return list of assignments with due dates (and optional submission status).
        Each item: student_name, course_name, title, due_datetime, status (optional).
        """
        if not self._ensure_credentials():
            return []

        results = []

        try:
            courses_resp = self._service.courses().list(studentId="me").execute()
            courses = courses_resp.get("courses", [])
        except HttpError as e:
            self.logger.error(f"Classroom API courses.list failed for {self.student_name}: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error listing courses for {self.student_name}: {e}", exc_info=True)
            return []

        for course in courses:
            course_id = course.get("id")
            course_name = course.get("name", "Unknown")
            if not course_id:
                continue

            try:
                cw_resp = (
                    self._service.courses()
                    .courseWork()
                    .list(courseId=course_id)
                    .execute()
                )
                work_list = cw_resp.get("courseWork", [])
            except HttpError as e:
                self.logger.debug(f"courseWork.list failed for course {course_id}: {e}")
                continue
            except Exception as e:
                self.logger.debug(f"Error listing coursework for {self.student_name}: {e}")
                continue

            for cw in work_list:
                if cw.get("state") != "PUBLISHED":
                    continue
                due_dt = _parse_due_date(
                    cw.get("dueDate"),
                    cw.get("dueTime"),
                )
                if due_dt is None:
                    continue
                due_date_only = due_dt.date()
                today = date.today()
                if not include_overdue and due_date_only < today:
                    continue

                # Optional: fetch submission state
                status = None
                if fetch_submission_status:
                    try:
                        sub_list = (
                            self._service.courses()
                            .courseWork()
                            .studentSubmissions()
                            .list(
                                courseId=course_id,
                                courseWorkId=cw.get("id"),
                                userId="me",
                            )
                            .execute()
                        )
                        subs = sub_list.get("studentSubmissions", [])
                        if subs:
                            state = subs[0].get("state")
                            if state == "TURNED_IN" or state == "RETURNED":
                                status = "Turned in"
                            else:
                                status = "Not turned in"
                    except Exception:
                        pass

                results.append({
                    "student_name": self.student_name,
                    "course_name": course_name,
                    "title": cw.get("title", "Assignment"),
                    "due_datetime": due_dt,
                    "status": status,
                })
        return results
