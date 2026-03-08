import json
from datetime import datetime

data = json.load(open('storage_state.json'))
for c in data['cookies']:
    exp = c.get('expires', -1)
    if exp > 0:
        print(f"{c['name']}: {datetime.fromtimestamp(exp)}")
    else:
        print(f"{c['name']}: Session（关闭浏览器失效）")
