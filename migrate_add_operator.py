#!/usr/bin/env python3
"""迁移脚本：为四张配置表添加 operator 字段"""
from sqlalchemy import inspect, text
import sys
sys.path.insert(0, '.')
from backend.database import db
from backend.app import create_app

app = create_app()
with app.app_context():
    insp = inspect(db.engine)
    for table in ['general_config', 'proxy_config', 'fingerprint_pool', 'preserved_env']:
        cols = [c['name'] for c in insp.get_columns(table)]
        if 'operator' not in cols:
            db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN operator VARCHAR(64) NOT NULL DEFAULT ""'))
            print(f'Added operator column to {table}')
        else:
            print(f'operator column already exists in {table}')
    db.session.commit()
    print('Migration complete.')
