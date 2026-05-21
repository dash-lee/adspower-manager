#!/usr/bin/env python3
"""迁移脚本：为 users 表添加 permissions 字段（绕过模型直接操作引擎）"""
import sqlite3
conn = sqlite3.connect('/mnt/e/Web/adspower-manager/data/adspower_manager.db')
cols = [c[1] for c in conn.execute('PRAGMA table_info(users)').fetchall()]
if 'permissions' not in cols:
    conn.execute("ALTER TABLE users ADD COLUMN permissions TEXT NOT NULL DEFAULT '[]'")
    conn.commit()
    print('Added permissions column to users table')
else:
    print('permissions column already exists')
conn.close()
