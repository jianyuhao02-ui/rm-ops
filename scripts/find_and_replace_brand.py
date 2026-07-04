#!/usr/bin/env python3
"""
scripts/find_and_replace_brand.py

此脚本扫描仓库中文本文件，查找并报告包含以下关键字的文件：
 - 'samsung' (不区分大小写)
 - 'SAMSUNG_'
 - 'Samsung'
 - '三星'

并可在 --apply 模式下替换为：
 - 'samsung' -> 'rm'
 - 'SAMSUNG_' -> 'RM_'
 - 'Samsung' -> 'RM'
 - '三星' -> '零售管理'

注意：脚本会跳过二进制文件（如 .png/.jpg/.pptx/.woff 等）。请在运行前备份仓库。
"""
import argparse
import os
import re

BINARY_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.woff', '.woff2', '.ttf', '.otf', '.pdf', '.pptx', '.xlsx', '.xls', '.zip'}
REPLACEMENTS = [
    (re.compile(r'SAMSUNG_'), 'RM_'),
    (re.compile(r'samsung', re.I), 'rm'),
    (re.compile(r'Samsung'), 'RM'),
    (re.compile(r'三星'), '零售管理'),
    (re.compile(r'samsung_ops.db', re.I), 'rm_ops.db'),
    (re.compile(r'samsung-ops.log', re.I), 'rm-ops.log'),
]


def is_binary_file(path: str) -> bool:
    _, ext = os.path.splitext(path)
    return ext.lower() in BINARY_EXTS


def scan_and_replace(root: str, apply: bool = False):
    report = []
    for dirpath, dirnames, filenames in os.walk(root):
        # skip .git and virtual envs
        if '.git' in dirpath or 'backend\.venv' in dirpath or '.venv' in dirpath:
            continue
        for fname in filenames:
            fp = os.path.join(dirpath, fname)
            if is_binary_file(fp):
                continue
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                continue
            new_content = content
            changes = []
            for pattern, repl in REPLACEMENTS:
                if pattern.search(new_content):
                    new_content = pattern.sub(repl, new_content)
                    changes.append((pattern.pattern, repl))
            if changes:
                report.append((fp, changes))
                if apply:
                    with open(fp, 'w', encoding='utf-8') as f:
                        f.write(new_content)
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--apply', action='store_true', help='Apply replacements')
    args = p.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    report = scan_and_replace(root, apply=args.apply)
    if not report:
        print('No matches found.')
        return
    print(f'Found {len(report)} files with matches:')
    for fp, changes in report:
        print(f'- {fp}: {changes}')
    if args.apply:
        print('\nReplacements applied. Please review changes and run tests.')
    else:
        print('\nRun with --apply to actually replace strings.')


if __name__ == '__main__':
    main()
