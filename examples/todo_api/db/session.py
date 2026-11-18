import sqlalchemy


class Session:
    def __init__(self):
        self.engine = sqlalchemy.create_engine("sqlite://")

    def save(self, obj):
        return obj

    def rollback(self):
        pass
