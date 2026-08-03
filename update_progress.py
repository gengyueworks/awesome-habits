#!/usr/bin/env python3
"""update_progress.py — 从微信读书官方 API 拉书架，生成「真实阅读进度条」。
用于 awesome-habits 仓库（public）。

用法:
    python3 update_progress.py           # 用缓存的 /tmp/weread_shelf.json 刷新进度
    python3 update_progress.py --pull    # 重新从微信读书拉取书架
    python3 update_progress.py --push    # 刷新后自动 git commit + 推送（带代理重试）

进度定义: 书架中「习惯/自控/专注/自律/早起」相关书目里，标记为「已读完」的比例。
注意: 本仓库为 public，README 只展示「已读完」书目（主动晒出的阅读成果），
不展示在读/想读书目（个人隐私）。完整书架只写本地 habit-reading-shelf.md。
"""
import json
import re
import os
import sys
import subprocess
import datetime
import urllib.parse

REPO = os.path.dirname(os.path.abspath(__file__))
SHELF = "/tmp/weread_shelf.json"
KEY_FILE = os.path.expanduser("~/.weread_key")
README = os.path.join(REPO, "README.md")
SHELF_MD = os.path.join(REPO, "habit-reading-shelf.md")
PULL = "--pull" in sys.argv
PUSH = "--push" in sys.argv

# ---------- 筛选规则：习惯领域 ----------
strong = [
    r'习惯', r'福格', r'Tiny Habits', r'Atomic Habits', r'The Power of Habit', r'掌控习惯',
    r'微习惯', r'自控力', r'意志力', r'Willpower', r'自律', r'自律力', r'早起的奇迹', r'早起',
    r'坚毅', r'Grit', r'原子习惯', r'掌控', r'习惯的力量', r'Change Your Habits',
    r'专注', r'深度工作', r'Deep Work', r'注意力', r'拖延', r'拖延症', r'立刻行动',
    r'精力管理', r'The Power of Full Engagement', r'上瘾', r'Hooked', r'不可打扰',
    r'Indistractable', r'Better Than Before', r'瞬变', r'Switch', r'高效能人士的七个习惯',
    r'7 Habits', r'一平方米的静心', r'心流', r'Flow', r'微习惯', r'最重要的事', r'One Thing',
    r'吃掉那只青蛙', r'Eat That Frog', r'5 秒法则', r'5 Second Rule', r'掌控习惯',
    r'好习惯', r'坏习惯', r'习惯力', r'习惯决定命运', r'自律的力量', r'意志力训练',
    r'心流', r'刻意练习', r'Deliberate Practice', r'终身成长', r'Mindset', r'执行力',
]
strong_pat = re.compile('|'.join(strong), re.I)
noise = re.compile(
    r'营销|销售|文案|品牌|广告|写作|小说|散文|诗集|心理学入门|教材|考研|雅思|托福|医'
    r'|编程|Python|Java|英语单词|口语|听力|刷题|试卷|题库',
    re.I,
)
drop = re.compile(
    r'习惯性无助|风土|风俗|习性|审美习惯|生活习惯|健康习惯|饮食习惯|睡眠习惯'
    r'|茶|咖啡|酒|烟|狗|猫|育儿|儿童|学生|高考|中考|考研'
    r'|混乱：如何成为失控|掌控谈话|即兴演讲|不放弃的世界|投资最重要的事|经营最重要的事'
    r'|英语思维|告别写作拖延|上瘾2|为自己思考|超越不可能|全情投入|心流学习法'
    r'|pureflow|PureFlow|TED演讲|刘慈欣|吴恩达|Claude|提示词',
    re.I,
)

themes = [
    ("习惯养成 · 行为设计",
     r'习惯|福格|Tiny Habits|Atomic Habits|The Power of Habit|掌控习惯|原子习惯|微习惯'
     r'|习惯的力量|好习惯|坏习惯|习惯力|习惯决定命运|Change Your Habits|行为设计'),
    ("意志力 · 自控 · 自律",
     r'自控力|意志力|Willpower|自律|自律力|自控|意志力训练|自律的力量'),
    ("专注 · 拖延 · 执行力",
     r'专注|深度工作|Deep Work|注意力|拖延|拖延症|立刻行动|执行力|最重要的事|One Thing'
     r'|吃掉那只青蛙|Eat That Frog|5 秒法则|5 Second Rule|心流|Flow|刻意练习|Deliberate Practice'),
    ("早起 · 精力 · 心性",
     r'早起的奇迹|早起|精力管理|The Power of Full Engagement|坚毅|Grit|终身成长|Mindset|瞬变|Switch'),
    ("上瘾与反沉迷",
     r'上瘾|Hooked|不可打扰|Indistractable|Better Than Before|高效能人士的七个习惯|7 Habits'),
]


def keep_rule(t, a):
    if drop.search(t):
        return False
    strong_hit = bool(strong_pat.search(t) or strong_pat.search(a))
    if not strong_hit:
        return False
    if noise.search(t) and not strong_hit:
        return False
    return True


def clean_title(t):
    t = re.sub(r"\s*--\s*Anna['’]?s Archive.*$", '', t, flags=re.I)
    t = re.sub(r'\s*--\s*[0-9a-f]{12,}.*$', '', t, flags=re.I)
    t = re.sub(r'(新版|典藏版|全新增订本|珍藏本|套装全\d?册|青少版|漫画版|绘本版|注疏点评版|第\d版|'
               r'原书第\d版|全新升级版|全2册|（全2册）|解读版|专业解读版|精华篇|精读全集|实践篇|'
               r'思维分册|方式分册|珍藏本).*$', '', t)
    t = re.sub(r'[（(]$', '', t)
    t = re.sub(r'（[^（)）]*）$', '', t)
    return t.strip()


def pull():
    key = open(KEY_FILE).read().strip()
    r = subprocess.run(
        ["curl", "-sS", "-X", "POST", "https://i.weread.qq.com/api/agent/gateway",
         "-H", f"Authorization: Bearer {key}", "-H", "Content-Type: application/json",
         "-d", '{"api_name":"/shelf/sync","skill_version":"1.0.4"}', "-o", SHELF],
        capture_output=True, text=True)
    if r.returncode != 0:
        print("pull failed:", r.stderr)
        sys.exit(1)
    print("pulled shelf ->", SHELF)


def filter_books(books):
    grouped = {name: [] for name, _ in themes}
    grouped['其他相关'] = []
    seen = {}
    for b in books:
        t = b.get('title', '') or ''
        a = b.get('author', '') or ''
        f = b.get('finishReading', 0)
        ct = clean_title(t)
        k = (ct, a)
        if k in seen:
            if f == 1:
                seen[k][3] = 1
            continue
        if not keep_rule(t, a):
            seen[k] = [t, a, f, '_drop']
            continue
        seen[k] = [clean_title(t), a, f, None]
        placed = False
        for name, pat in themes:
            if re.search(pat, t) or re.search(pat, a):
                grouped[name].append(seen[k])
                placed = True
                break
        if not placed:
            grouped['其他相关'].append(seen[k])
    for key in grouped:
        grouped[key].sort(key=lambda x: (-x[2], x[0]))
    return grouped


def gen_progress(fin_n, total_n, fin_list):
    pct = fin_n / total_n * 100 if total_n else 0
    filled = round(pct / 100 * 20)
    bar = '█' * filled + '░' * (20 - filled)
    label = "习惯阅读进度"
    msg = f"{fin_n}/{total_n}"
    badge = ("https://img.shields.io/badge/"
             + urllib.parse.quote(label) + "-"
             + urllib.parse.quote(msg, safe='') + "-success")
    today = datetime.date.today().isoformat()
    L = []
    L.append("## 📊 我的真实阅读进度\n")
    L.append(f"> 数据由微信读书官方 API 实时拉取（最近同步：{today}），只统计书架里「习惯 / 自控 / 专注 / 早起」相关书目。"
             f"已读完标 ✓。每读完一本，重跑 `python3 update_progress.py` 进度条自动前进。\n")
    L.append(f"![{label}]({badge})\n")
    L.append(f"已完成 **{fin_n} / {total_n}** 本（{pct:.0f}%）\n")
    L.append(f"\n`{bar}` {pct:.0f}%\n")
    if fin_list:
        L.append(f"\n**✅ 已读完（{fin_n} 本）**\n")
        for t, a in fin_list:
            L.append(f"- ✓ **{t}** — {a}")
        L.append("")
    else:
        L.append("\n> 书架里还没有标记「已读完」的习惯类书目，正在读的路上。\n")
    L.append("> 完整书架数据仅作者本地可见（`habit-reading-shelf.md`，不推送）。"
             "运行 `python3 update_progress.py [--pull] [--push]` 可刷新。")
    return "\n".join(L)


def update_readme(block):
    s = open(README, encoding='utf-8').read()
    pat = re.compile(r'<!-- PROGRESS_START -->.*?<!-- PROGRESS_END -->', re.S)
    new = f"<!-- PROGRESS_START -->\n{block}\n<!-- PROGRESS_END -->"
    if pat.search(s):
        s = pat.sub(new, s)
    else:
        s += f"\n{new}\n"
    open(README, 'w', encoding='utf-8').write(s)


def main():
    if PULL or not os.path.exists(SHELF):
        pull()
    data = json.load(open(SHELF, encoding='utf-8'))
    books = data.get('books', [])
    grouped = filter_books(books)
    all_items = [x for v in grouped.values() for x in v]
    total = len(all_items)
    fin = [(t, a) for v in grouped.values() for (t, a, f, _) in v if f == 1]
    fin_n = len(fin)
    print(f"习惯相关: {total} 本, 已读完: {fin_n} 本 ({fin_n/total*100:.0f}%)")
    for name, items in grouped.items():
        if items:
            print(f"  [{name}] {len(items)} 本")
    block = gen_progress(fin_n, total, fin)
    update_readme(block)
    # 完整书架只写本地，不 git 跟踪（隐私）
    with open(SHELF_MD, 'w', encoding='utf-8') as f:
        f.write("# 我的微信读书书架 · 习惯领域实录（本地，勿推送）\n")
        f.write(f"> 习惯/自控/专注/早起相关 {total} 本（已读完 {fin_n} 本，标 ✓）。\n")
        for name, items in grouped.items():
            if not items:
                continue
            f.write(f"\n## {name}（{len(items)}）\n")
            for t, a, fr, _ in items:
                m = "✓ " if fr == 1 else ""
                f.write(f"- {m}**{t}** — {a}")
            f.write("\n")
    print("updated README progress block + habit-reading-shelf.md (local)")
    if PUSH:
        proxy = os.environ.get('HTTPS_PROXY', 'http://127.0.0.1:21879')
        subprocess.run(['git', 'config', 'http.proxy', proxy], cwd=REPO)
        subprocess.run(['git', 'config', 'http.version', 'HTTP/1.1'], cwd=REPO)
        subprocess.run(['git', 'config', 'http.postBuffer', '524288000'], cwd=REPO)
        subprocess.run(['git', 'add', '-A'], cwd=REPO)
        subprocess.run(['git', 'commit', '-m', f'progress: 更新阅读进度 {fin_n}/{total}'], cwd=REPO)
        for i in range(3):
            r = subprocess.run(['git', 'push', 'origin', 'main'], cwd=REPO, capture_output=True, text=True)
            if r.returncode == 0:
                print("pushed")
                break
            print("push retry", i + 1, r.stderr[-200:] if r.stderr else '')


if __name__ == '__main__':
    main()
