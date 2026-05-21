#!/usr/bin/env python3
"""迁移脚本：为 users 表添加 permissions 字段"""
from sqlalchemy import inspect, text
import sys
sys.path.insert(0, '.')
from backend.database import db
from backend.app import create_app

app = create_app()
with app.app_context():
    insp = inspect(db.engine)
    cols = [c['name'] for c in insp.get_columns('users')]
    if 'permissions' not in cols:
        db.session.execute(text("ALTER TABLE users ADD COLUMN permissions TEXT NOT NULL DEFAULT '[]'"))
        db.session.commit()
        print('Added permissions column to users')
    else:
        print('permissions column already exists in users')
