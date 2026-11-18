from services.tasks import TaskService
from db.models import User


def test_create():
    assert TaskService().create(User(), "x").title == "x"
