# 星尘笔记 · Stardust Notes

> 每夜八点，一篇经过交叉验证的 AI 前沿洞察。
> 在信息洪流中打捞真相。

---

## 项目结构

```
blog/
├── index.html              # 博客主页 (JSON驱动，动态渲染)
├── article.html            # 文章详情页
├── articles.json           # 文章数据库
├── rss.xml                 # RSS 2.0 订阅源
├── sitemap.xml             # 搜索引擎站点地图
├── schedule_task.ps1       # Windows 每日定时任务脚本
├── README.md               # 本文件
└── generator/
    ├── fetch_news.py       # 内容生成引擎
    ├── sources.yaml        # 信源配置 (7个AI新闻RSS源)
    └── requirements.txt    # Python 依赖
```

## 快速开始

### 1. 本地预览

```bash
# 使用 Python 内置服务器
cd blog
python -m http.server 8080

# 浏览器打开 http://localhost:8080
```

### 2. 内容生成（需要 Anthropic API Key）

```bash
# 安装依赖
pip install -r generator/requirements.txt

# 设置 API Key
set ANTHROPIC_API_KEY=your-key-here

# 预览模式（不保存）
python generator/fetch_news.py --dry-run

# 生成文章
python generator/fetch_news.py --max-articles 2
```

### 3. 设置每日自动更新

```powershell
# 以管理员身份运行 PowerShell
powershell -ExecutionPolicy Bypass -File schedule_task.ps1
```

## 部署

### 方案一：GitHub Pages（免费）

```bash
cd blog
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/你的用户名/你的仓库.git
git push -u origin main
# 在仓库 Settings > Pages 中启用 GitHub Pages
```

### 方案二：Vercel（免费，推荐）

1. 将 blog 目录上传到 GitHub
2. 在 [vercel.com](https://vercel.com) 导入仓库
3. 无需配置 — 自动部署纯静态站点

### 方案三：Netlify（免费）

拖拽 `blog/` 目录到 [netlify.com](https://netlify.com) 即可。

## 自动部署流水线

完整自动化流程：
1. **每晚 20:00** — Windows 任务计划运行 `fetch_news.py`
2. **Python 脚本** — 从 7 个 RSS 源抓取 AI 新闻
3. **交叉验证** — 至少 2 个独立来源确认才采用
4. **Claude API** — 基于真实新闻生成中文深度文章
5. **自动输出** — 追加到 `articles.json`，更新 `rss.xml`
6. **Git 自动推送**（可选）— 自动 commit 并 push 触发 Vercel 部署

## 信源列表

| 信源 | 权重 |
|------|------|
| TechCrunch AI | 3 |
| MIT Technology Review | 3 |
| Ars Technica AI | 3 |
| The Verge AI | 2 |
| VentureBeat AI | 2 |
| ZDNet AI | 2 |
| Hacker News (HN) | 1 |

**交叉验证规则**：每条新闻至少被 2 个独立信源报道，才会被采用。

## 技术栈

- 纯静态 HTML/CSS/JS（零后端，无限扩展）
- Canvas 星空粒子背景
- JSON 驱动的文章渲染
- RSS 2.0 + Sitemap XML
- Open Graph / Twitter Card / JSON-LD 结构化数据
- Python 内容生成引擎（feedparser + Claude API）

## 自定义域名

1. 在域名提供商处添加 CNAME 记录指向你的部署地址
2. 在 Vercel/Netlify/GitHub Pages 设置中添加自定义域名
3. 修改 `index.html` 中的 `og:url` 和 `sitemap.xml` 中的 URL
4. 修改 `generator/fetch_news.py` 中的 `site_url` 变量

## 许可

代码：MIT License
图片：来自 [Unsplash](https://unsplash.com) 免费商用许可
