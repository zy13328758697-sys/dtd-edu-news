#!/usr/bin/env python3
"""
德英乐教育·教育行业资讯 — 每日自动更新脚本
由 GitHub Actions 每天定时触发运行
"""

import json
import os
import re
import time
import requests
from datetime import datetime, timezone, timedelta
from ddgs import DDGS

# ============================================================
# 配置
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "template.html")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "docs", "index.html")

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

# 北京时间
BJT = timezone(timedelta(hours=8))

# 搜索关键词（每个板块2组，共8次搜索）
SEARCH_QUERIES = [
    {"cat": "policy",  "q": "中国 教育政策 教育部 民办学校 最新 2026"},
    {"cat": "policy",  "q": "K12 双语学校 国际学校 政策 监管 规范"},
    {"cat": "trend",   "q": "教育行业 市场动态 AI教育 招生 培训 2026"},
    {"cat": "trend",   "q": "民办教育 上市公司 教育科技 竞争 新闻"},
    {"cat": "intl",    "q": "国际教育 留学 双语教育 课程 IB AP A-Level"},
    {"cat": "intl",    "q": "international education China K12 bilingual school"},
    {"cat": "shanghai","q": "上海 国际学校 双语学校 招生 入学 2026"},
    {"cat": "shanghai","q": "上海 民办学校 教育 开放日 升学 新闻"},
]


def log(msg):
    print(f"[{datetime.now(BJT).strftime('%H:%M:%S')}] {msg}")


# ============================================================
# 第一步：搜索新闻
# ============================================================

def search_ddg(query, num=5):
    """调用 DuckDuckGo 搜索（免费，无需API Key）"""
    results = []
    try:
        items = DDGS().text(query, region="cn-zh", max_results=num)
        for item in items:
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("body", ""),
                "source": item.get("href", "").split("/")[2] if "/" in item.get("href", "") else "",
                "url": item.get("href", ""),
            })
    except Exception as e:
        log(f"  DuckDuckGo搜索异常: {e}")
    return results


def fetch_all_news():
    """按板块抓取所有新闻"""
    grouped = {}
    for sq in SEARCH_QUERIES:
        cat = sq["cat"]
        if cat not in grouped:
            grouped[cat] = []
        try:
            results = search_ddg(sq["q"], num=6)
            grouped[cat].extend(results)
            log(f"  [{cat}] 搜到 {len(results)} 条")
            time.sleep(1)  # 避免请求过快
        except Exception as e:
            log(f"  [{cat}] 搜索失败: {e}")

    # 去重
    for cat in grouped:
        seen = set()
        unique = []
        for item in grouped[cat]:
            if item["title"] and item["title"] not in seen:
                seen.add(item["title"])
                unique.append(item)
        grouped[cat] = unique[:8]

    return grouped


# ============================================================
# 第二步：AI 生成结构化内容
# ============================================================

def call_deepseek(all_news):
    """调用 DeepSeek API 生成日报内容"""
    today = datetime.now(BJT)
    date_str = f"{today.strftime('%Y年%m月%d日')} {WEEKDAY_CN[today.weekday()]}"

    prompt = f"""你是德英乐教育集团的教育行业分析师。今天是{date_str}。

德英乐教育集团简介：上海K-12一贯制双语教育集团，旗下有多所万科双语学校（闵行、浦东等），中小学实行双语制度，高中聚焦海外升学，获IB PYP、CAIE等国际认证。

请基于以下新闻素材，生成一份教育行业日报。

【要求】
1. 从素材中筛选8-10条最有价值的新闻（与K12、双语教育、国际教育、教育政策、AI教育相关）
2. 分为四个板块：
   - 政策与监管动态（2-3条）
   - 行业趋势与市场（2-3条）
   - 国际教育视野（2-3条）
   - 教育深度观察（1-2条）
3. 每条新闻包含：tag（2-4字标签）、tag_class（CSS类名，从以下选择：t-policy/t-ministry/t-enroll/t-compete/t-conf/t-lang/t-insight/t-trend/t-ai）、title、summary（100-150字）、perspective（德英乐视角，40-60字）、source、date、url（新闻原文链接，直接使用素材中提供的url）
4. 从上海相关新闻中提取6-10条作为"上海专栏"，每条包含tag、title、desc、source_date、url字段
5. 输出纯JSON，不要markdown代码块

【新闻素材】
{json.dumps(all_news, ensure_ascii=False)}

【输出格式】
{{"sections":[{{"name":"政策与监管动态","news":[{{"tag":"政策聚焦","tag_class":"t-policy","title":"...","summary":"...","perspective":"...","source":"来源","date":"2026-03-18","url":"https://..."}}]}}],"shanghai":[{{"tag":"政策","title":"...","desc":"...","source_date":"来源 · 03-18","url":"https://..."}}]}}"""

    resp = requests.post(
        "https://api.deepseek.com/v1/chat/completions",
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 4000,
        },
        headers={
            "Authorization": f"Bearer {DEEPSEEK_KEY}",
            "Content-Type": "application/json",
        },
        timeout=90,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]

    # 提取JSON（兼容有无代码块的情况）
    content = re.sub(r'^```json\s*', '', content.strip())
    content = re.sub(r'\s*```$', '', content.strip())
    json_match = re.search(r'\{[\s\S]*\}', content)
    if json_match:
        return json.loads(json_match.group())
    raise ValueError("AI返回内容无法解析为JSON")


# ============================================================
# 第三步：渲染 HTML
# ============================================================

def render_html(data):
    today = datetime.now(BJT)
    date_str = f"{today.strftime('%Y年%m月%d日')} {WEEKDAY_CN[today.weekday()]}"
    date_iso = today.strftime('%Y-%m-%d')

    # 计算期号：从2026-03-18起，仅计算工作日
    start_date = datetime(2026, 3, 18, tzinfo=BJT)
    issue_num = 1
    d = start_date
    while d.date() < today.date():
        d += timedelta(days=1)
        if d.weekday() < 5:  # 周一到周五
            issue_num += 1
    issue = f"{issue_num:03d}"

    # 生成新闻板块HTML
    sec_icons = ["navy", "gold", "navy", "gold"]
    sec_ids = ["s-policy", "s-trend", "s-intl", "s-insight"]
    sections_html = ""
    total_news = 0

    for i, section in enumerate(data.get("sections", [])):
        icon = sec_icons[i % len(sec_icons)]
        sid = sec_ids[i] if i < len(sec_ids) else f"s-{i}"
        sections_html += f'<div class="sec-head" id="{sid}"><div class="sec-icon {icon}"></div><div class="sec-title">{section.get("name", "")}</div><div class="sec-line"></div></div>\n<div class="news-list">\n'

        for j, news in enumerate(section.get("news", [])):
            tc = news.get("tag_class", "t-policy")
            featured_cls = " featured" if j == 0 else ""
            url = news.get("url", "#")
            sections_html += f'''<div class="ncard{featured_cls}" data-tag="{tc}">
<div class="ncard-body">
<div class="ncard-tag {tc}">{news.get("tag", "资讯")}</div>
<div class="ncard-title"><a href="{url}" target="_blank" rel="noopener">{news.get("title", "")}</a></div>
<div class="ncard-summary">{news.get("summary", "")}</div>
<div class="ncard-meta"><span>来源：{news.get("source","")}</span><span>{news.get("date","")}</span><a class="ncard-source-link" href="{url}" target="_blank" rel="noopener">阅读原文 →</a></div>
</div>
<div class="ncard-persp"><div class="persp-label">德英乐视角</div>
<div class="persp-text">{news.get("perspective", "")}</div></div>
</div>\n'''
            total_news += 1

        sections_html += '</div>\n'

    # 生成上海专栏HTML
    sh_items = data.get("shanghai", [])
    sh_count = len(sh_items)
    sh_html = ""
    for idx, item in enumerate(sh_items):
        collapsed_cls = " collapsed" if idx >= 5 else ""
        url = item.get("url", "#")
        sh_html += f'''<div class="sh-item{collapsed_cls}">
<div class="sh-item-tag">{item.get("tag", "资讯")}</div>
<div class="sh-item-title"><a href="{url}" target="_blank" rel="noopener">{item.get("title", "")}</a></div>
<div class="sh-item-desc">{item.get("desc", item.get("description", ""))}</div>
<div class="sh-item-meta">{item.get("source_date", item.get("source", ""))} · <a class="ncard-source-link" href="{url}" target="_blank" rel="noopener">原文</a></div>
</div>\n'''

    # 读取模板并替换
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    html = html.replace("{{DATE}}", date_str)
    html = html.replace("{{DATE_ISO}}", date_iso)
    html = html.replace("{{ISSUE}}", issue)
    html = html.replace("{{SECTIONS}}", sections_html)
    html = html.replace("{{SHANGHAI}}", sh_html)
    html = html.replace("{{NEWS_COUNT}}", str(total_news))
    html = html.replace("{{SH_COUNT}}", str(sh_count))

    return html


def save(html):
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"已保存: {OUTPUT_PATH}")


# ============================================================
# 主流程
# ============================================================

def main():
    today = datetime.now(BJT)
    log(f"===== 教育日报自动更新 {today.strftime('%Y-%m-%d')} =====")

    if not DEEPSEEK_KEY:
        log("❌ 错误：缺少API密钥！")
        log("请在GitHub仓库 Settings → Secrets → Actions 中添加 DEEPSEEK_API_KEY")
        raise SystemExit(1)

    log(f"✓ API密钥已配置（长度={len(DEEPSEEK_KEY)}）")

    # 第1步：搜索新闻
    log("第1步：搜索新闻...")
    try:
        all_news = fetch_all_news()
        total = sum(len(v) for v in all_news.values())
        log(f"✓ 共抓取 {total} 条新闻")
        if total == 0:
            log("⚠ 警告：未搜到任何新闻，可能是网络问题，将使用空数据继续")
    except Exception as e:
        log(f"❌ 搜索新闻失败: {e}")
        raise

    # 第2步：AI生成内容
    log("第2步：调用DeepSeek AI生成内容...")
    try:
        structured = call_deepseek(all_news)
        news_count = sum(len(s.get("news", [])) for s in structured.get("sections", []))
        sh_count = len(structured.get("shanghai", []))
        log(f"✓ 生成 {news_count} 条主新闻 + {sh_count} 条上海专栏")
    except requests.exceptions.HTTPError as e:
        log(f"❌ DeepSeek API调用失败！HTTP状态码: {e.response.status_code}")
        log(f"   响应内容: {e.response.text[:500]}")
        if e.response.status_code == 401:
            log("   原因：API Key无效或已过期，请检查DEEPSEEK_API_KEY是否正确")
        elif e.response.status_code == 402:
            log("   原因：账户余额不足，请登录 platform.deepseek.com 充值")
        elif e.response.status_code == 429:
            log("   原因：请求频率超限，请稍后重试")
        raise
    except Exception as e:
        log(f"❌ AI生成内容失败: {type(e).__name__}: {e}")
        raise

    # 第3步：渲染HTML
    log("第3步：渲染HTML...")
    try:
        html = render_html(structured)
        log(f"✓ HTML生成完成（{len(html)} 字符）")
    except Exception as e:
        log(f"❌ 渲染HTML失败: {e}")
        raise

    # 第4步：保存文件
    log("第4步：保存文件...")
    try:
        save(html)
        log("✓ 文件保存成功")
    except Exception as e:
        log(f"❌ 保存文件失败: {e}")
        raise

    log("===== ✓ 全部完成! =====")


if __name__ == "__main__":
    main()
