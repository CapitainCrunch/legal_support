from peewee import *
from datetime import datetime
from config import MYSQL_CONN

db = MySQLDatabase(**MYSQL_CONN)

def before_request_handler():
    db.connect()

def after_request_handler():
    db.close()

class BaseModel(Model):
    id = PrimaryKeyField()
    dt = DateTimeField(default=datetime.now())
    class Meta:
        database = db

class Users(BaseModel):
    telegram_id = IntegerField(unique=1)
    username = CharField(null=True)
    current_password = CharField(null=True)
    name = CharField()


class Company(BaseModel):
    name = CharField(unique=1)
    description = TextField()
    url = CharField(null=True)


class Good(BaseModel):
    name = CharField(unique=1)
    description = TextField()
    url = CharField(null=True)


class Service(BaseModel):
    name = CharField(unique=1)
    description = TextField()
    url = CharField(null=True)


class UndefinedRequests(BaseModel):
    from_user = ForeignKeyField(Users,
                                  to_field='telegram_id')
    request = CharField()


class Aliases(BaseModel):
    key = CharField(unique=1)
    alias1 = CharField(null=True)
    alias2 = CharField(null=True)
    alias3 = CharField(null=True)
    alias4 = CharField(null=True)
    alias5 = CharField(null=True)
    alias6 = CharField(null=True)
    alias7 = CharField(null=True)
    alias8 = CharField(null=True)
    alias9 = CharField(null=True)
    alias10 = CharField(null=True)


class Passwords(BaseModel):
    password = CharField(unique=1)
    active = BooleanField(default=True)


def init_db():
    tables = [Users, Company, Good, Service, UndefinedRequests, Aliases, Passwords]
    for t in tables:
        if t.table_exists():
            t.drop_table()
        t.create_table()
    Passwords.create(password='MCCLegalSupport17', active=1)


def save(data, db_name):
    """
    Initialize table.
    Batch insert rows
    :param texts_stats:
    :return:
    """

    with db.atomic():
        db_name.insert_many(data).upsert().execute()
    return True


if __name__ == '__main__':
    init_db()
    print('Таблицы создал')