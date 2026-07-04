"""修复 scheduler_service.py 中的 DB_PATH 引用"""
import os

path = os.path.join(os.path.dirname(__file__), "..", "backend", "services", "scheduler_service.py")
path = os.path.abspath(path)

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 替换所有 DB_PATH 引用为 DB_PATH_STR（但保留 import 和定义行）
lines = content.split("\n")
new_lines = []
for line in lines:
    # 跳过 import 和定义行
    if "from backend.config import" in line or "DB_PATH_STR = str" in line:
        new_lines.append(line)
        continue
    # 替换引用
    line = line.replace("aiosqlite.connect(DB_PATH)", "aiosqlite.connect(DB_PATH_STR)")
    line = line.replace("os.path.exists(DB_PATH)", "os.path.exists(DB_PATH_STR)")
    line = line.replace("shutil.copy2(DB_PATH,", "shutil.copy2(DB_PATH_STR,")
    new_lines.append(line)

with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(new_lines))

print("Done - scheduler_service.py references fixed")
