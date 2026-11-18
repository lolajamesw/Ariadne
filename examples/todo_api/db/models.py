class Base:
    id: int = 0


class User(Base):
    name: str = ""


class Task(Base):
    def __init__(self, owner: User, title: str):
        self.owner: User = owner
        self.title = title
        self.done = False
