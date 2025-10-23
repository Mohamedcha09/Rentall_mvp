from alembic.config import Config
from alembic import command

cfg = Config('alembic.ini')
command.upgrade(cfg, 'head')
print('? migration done')
