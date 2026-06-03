import sys
sys.path.insert(0,'/app/backend')
import sqlite3
from open_webui.utils.auth import get_password_hash
DB="/app/backend/data/webui.db"
c=sqlite3.connect(DB); cur=c.cursor()
pwd=get_password_hash("admin")
uid=cur.execute("SELECT id FROM user ORDER BY created_at LIMIT 1").fetchone()[0]
cur.execute("UPDATE user SET email='admin@localhost' WHERE id=?", (uid,))
cur.execute("UPDATE auth SET email='admin@localhost', password=?, active=1 WHERE id=?", (pwd, uid))
c.commit()
print("user:", cur.execute("SELECT name,email,role FROM user").fetchall())
print("auth:", cur.execute("SELECT email,active FROM auth").fetchall())
