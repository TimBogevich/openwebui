import sqlite3, time
c=sqlite3.connect('/app/backend/data/webui.db'); cur=c.cursor()
content=open('/tmp/gcu_filter.py',encoding='utf-8').read()
# function table uses int epoch (NOT config's datetime!)
cur.execute("UPDATE function SET content=?, updated_at=? WHERE id='gcu_report_filter'",
            (content, int(time.time())))
c.commit()
print("filter content updated, len:", len(content))
print("has native-skip:", "function_calling" in content and "tools" in content)
