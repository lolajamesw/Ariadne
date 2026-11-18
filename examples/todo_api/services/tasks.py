from db.models import Task, User
from db.session import Session


class TaskService:
    def __init__(self):
        self.session: Session = Session()
        self.last_task: Task | None = None

    def create(self, user: User, title: str) -> Task:
        task = Task(owner=user, title=title)
        self.session.save(task)
        self.last_task = task
        return task

    def complete(self, task: Task) -> None:
        try:
            task.done = True
            self.session.save(task)
        except Exception:
            self.session.rollback()
