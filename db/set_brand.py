# -*- coding: utf-8 -*-
"""
Set RZD branding identity in the Open WebUI database.

Two distinct identities (this was the source of the duplicate "РЖД Интер"):
  • ui.name        -> the APP name, shown in the sidebar HEADER  = "РЖД Интер"
  • user.name      -> the logged-in USER, shown in the FOOTER    = "Оператор"
  • profile_image_url -> footer avatar -> /static/rzd_user.png   (file that EXISTS)

Run inside the OWI container, e.g.:
  docker exec -i open-webui python - < db/set_brand.py
or for the native Windows deploy, point DB at c:\\llm\\openwebui\\data\\webui.db
"""
import sqlite3, json, os

DB = os.environ.get("OWI_DB", "/app/backend/data/webui.db")

APP_NAME   = "РЖД Интер"            # header / browser title / app name
USER_NAME  = "Оператор"            # footer profile name (change as you like)
USER_AVATAR = "/static/rzd_user.png"  # NOTE: rzd_user.png, not user.png

c = sqlite3.connect(DB); cur = c.cursor()

# ---- footer identity: the admin user (name + avatar) ----
cur.execute(
    "UPDATE user SET profile_image_url=?, name=? WHERE role='admin'",
    (USER_AVATAR, USER_NAME),
)

# ---- header identity: the app name in config.ui.name ----
cid, data = cur.execute(
    "SELECT id, data FROM config ORDER BY id DESC LIMIT 1"
).fetchone()
d = json.loads(data)
d.setdefault("ui", {})["name"] = APP_NAME
cur.execute(
    "UPDATE config SET data=?, updated_at=created_at WHERE id=?",
    (json.dumps(d, ensure_ascii=False), cid),
)

c.commit()
print("ui.name (header) :", APP_NAME)
print("user (footer)    :", cur.execute(
    "SELECT name, profile_image_url FROM user WHERE role='admin'").fetchall())
c.close()
