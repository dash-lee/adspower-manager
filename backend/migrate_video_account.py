"""
数据库迁移：在 videos 表添加 account_name 字段
"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'adspower_manager.db')
conn = sqlite3.connect(db_path)
c = conn.cursor()

# 检查列是否已存在
cols = [col[1] for col in c.execute("PRAGMA table_info(videos)").fetchall()]
if 'account_name' not in cols:
    c.execute("ALTER TABLE videos ADD COLUMN account_name TEXT NOT NULL DEFAULT ''")
    print("✓ 已添加 account_name 字段")
else:
    print("- account_name 字段已存在")

# 检查 videos 表是否有账号名称索引
c.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='videos' AND name='idx_videos_account_name'")
if not c.fetchone():
    c.execute("CREATE INDEX idx_videos_account_name ON videos(account_name)")
    print("✓ 已添加 account_name 索引")
else:
    print("- idx_videos_account_name 索引已存在")

# 为 general_config 添加索引
c.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='general_config' AND name='idx_general_config_category'")
if not c.fetchone():
    c.execute("CREATE INDEX idx_general_config_category ON general_config(category)")
    print("✓ 已添加 general_config.category 索引")
else:
    print("- idx_general_config_category 索引已存在")

# 为 proxy_config 添加索引
for idx_name, col_name in [('idx_proxy_config_enabled', 'enabled'), ('idx_proxy_config_proxy_soft', 'proxy_soft')]:
    c.execute(f"SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='proxy_config' AND name='{idx_name}'")
    if not c.fetchone():
        c.execute(f"CREATE INDEX {idx_name} ON proxy_config({col_name})")
        print(f"✓ 已添加 proxy_config.{col_name} 索引")
    else:
        print(f"- {idx_name} 索引已存在")

# 为 users 表添加 is_active 索引
c.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='users' AND name='idx_users_is_active'")
if not c.fetchone():
    c.execute("CREATE INDEX idx_users_is_active ON users(is_active)")
    print("✓ 已添加 users.is_active 索引")
else:
    print("- idx_users_is_active 索引已存在")

# 为 operation_log 添加复合索引
c.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='operation_log' AND name='idx_operation_log_level_module'")
if not c.fetchone():
    c.execute("CREATE INDEX idx_operation_log_level_module ON operation_log(level, module)")
    print("✓ 已添加 operation_log.level+module 复合索引")
else:
    print("- idx_operation_log_level_module 索引已存在")

conn.commit()
conn.close()
print("\n迁移完成")
