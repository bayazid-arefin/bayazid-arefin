"""Generate GitHub stats cards (light + dark) that include private and
organization repositories. Shows only the numbers worth showing."""
import json
import os
import urllib.request
from html import escape

TOKEN = os.environ["GH_TOKEN"]
IGNORED_LANGS = {"HTML", "CSS", "SCSS"}
ACCENT = "#E8541F"

THEMES = {
    "dark": dict(bg="#0D1117", border="#30363D", title="#F5F5F4", num="#F5F5F4",
                 label="#A8A29E", track="#21262D"),
    "light": dict(bg="#FFFFFF", border="#F1E4DC", title="#111111", num="#111111",
                  label="#57534E", track="#F5F0EC"),
}


def gql(query, variables=None):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        data = json.load(r)
    if "errors" in data:
        raise SystemExit(json.dumps(data["errors"], indent=2))
    return data["data"]


def fetch():
    base = gql("""{ viewer {
        login
        pullRequests { totalCount }
        contributionsCollection { contributionYears }
    } }""")["viewer"]

    commits = contributions = 0
    for year in base["contributionsCollection"]["contributionYears"]:
        c = gql("""query($from: DateTime!, $to: DateTime!) { viewer {
            contributionsCollection(from: $from, to: $to) {
              totalCommitContributions
              contributionCalendar { totalContributions }
            } } }""", {"from": f"{year}-01-01T00:00:00Z",
                       "to": f"{year}-12-31T23:59:59Z"})["viewer"]["contributionsCollection"]
        commits += c["totalCommitContributions"]
        contributions += c["contributionCalendar"]["totalContributions"]

    repos, langs, cursor = 0, {}, None
    while True:
        page = gql("""query($after: String) { viewer {
            repositories(first: 100, after: $after, isFork: false,
                         ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]) {
              totalCount
              pageInfo { hasNextPage endCursor }
              nodes { languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
                edges { size node { name color } } } }
            } } }""", {"after": cursor})["viewer"]["repositories"]
        repos = page["totalCount"]
        for node in page["nodes"]:
            for e in node["languages"]["edges"]:
                name = e["node"]["name"]
                if name in IGNORED_LANGS:
                    continue
                entry = langs.setdefault(name, {"size": 0, "color": e["node"]["color"] or "#8B949E"})
                entry["size"] += e["size"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    return {
        "stats": [
            ("Contributions", contributions),
            ("Commits", commits),
            ("Pull Requests", base["pullRequests"]["totalCount"]),
            ("Repositories", repos),
        ],
        "langs": langs,
    }


def render(data, t):
    W, H = 840, 250
    # keep only non-zero stats so the card never shows a 0
    stats = [(k, v) for k, v in data["stats"] if v > 0]
    total = sum(v["size"] for v in data["langs"].values()) or 1
    langs = sorted(data["langs"].items(), key=lambda kv: -kv[1]["size"])[:6]

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
           '<style>text{font-family:"Segoe UI",Ubuntu,"Helvetica Neue",Arial,sans-serif}</style>',
           f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="10" fill="{t["bg"]}" stroke="{t["border"]}"/>',
           f'<text x="28" y="40" font-size="17" font-weight="600" fill="{t["title"]}">GitHub Overview</text>',
           f'<text x="{W-28}" y="40" font-size="12" text-anchor="end" fill="{t["label"]}">Including private &amp; organization repositories</text>']

    # stat tiles
    if stats:
        col = (W - 56) / len(stats)
        for i, (label, value) in enumerate(stats):
            cx = 28 + col * i + col / 2
            out.append(f'<text x="{cx:.0f}" y="100" font-size="30" font-weight="700" text-anchor="middle" fill="{t["num"]}">{value:,}</text>')
            out.append(f'<text x="{cx:.0f}" y="124" font-size="13" text-anchor="middle" fill="{t["label"]}">{label}</text>')
            if i:
                x = 28 + col * i
                out.append(f'<line x1="{x:.0f}" y1="72" x2="{x:.0f}" y2="130" stroke="{t["border"]}"/>')

    # languages bar
    out.append(f'<text x="28" y="168" font-size="13" font-weight="600" fill="{ACCENT}">Most used languages</text>')
    bar_x, bar_w, y = 28, W - 56, 180
    out.append(f'<clipPath id="bar"><rect x="{bar_x}" y="{y}" width="{bar_w}" height="10" rx="5"/></clipPath>')
    out.append(f'<rect x="{bar_x}" y="{y}" width="{bar_w}" height="10" rx="5" fill="{t["track"]}"/>')
    x = bar_x
    for name, v in langs:
        w = bar_w * v["size"] / total
        out.append(f'<rect clip-path="url(#bar)" x="{x:.2f}" y="{y}" width="{w:.2f}" height="10" fill="{v["color"]}"/>')
        x += w
    # legend
    per = (W - 56) / max(len(langs), 1)
    for i, (name, v) in enumerate(langs):
        lx = 28 + per * i
        pct = 100 * v["size"] / total
        out.append(f'<circle cx="{lx+5:.0f}" cy="217" r="5" fill="{v["color"]}"/>')
        out.append(f'<text x="{lx+16:.0f}" y="221" font-size="12.5" fill="{t["num"]}">{escape(name)} '
                   f'<tspan fill="{t["label"]}">{pct:.1f}%</tspan></text>')
    out.append('</svg>')
    return "\n".join(out)


if __name__ == "__main__":
    data = fetch()
    for name, theme in THEMES.items():
        with open(f"stats-{name}.svg", "w") as f:
            f.write(render(data, theme))
    print(json.dumps(data["stats"]))
