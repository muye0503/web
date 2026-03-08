import json
from datetime import datetime

cookies = json.load(open('cookies.json'))
for c in cookies:
    exp = c.get('expires', -1)
    if exp > 0:
        print(f"{c['name']}: {datetime.fromtimestamp(exp)}")
    else:
        print(f"{c['name']}: Session（关闭浏览器失效）")
