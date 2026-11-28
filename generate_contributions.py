#!/usr/bin/env python3
"""
Generates contributions.svg - a cyberpunk contribution-status panel
styled to match banner.svg (Nikki Senpai profile).

Usage:
  GH_TOKEN=xxx python generate_contributions.py            # live data
  python generate_contributions.py --demo                  # fake data preview
"""
import os, sys, json, random, urllib.request
from html import escape
from datetime import date, datetime, timedelta, timezone

LOGIN = os.environ.get("GH_LOGIN", "nikkisenpai27")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
OUT = os.environ.get("OUT", "contributions.svg")
DEMO = "--demo" in sys.argv
STATIC = "--static" in sys.argv  # standalone SVG with hand-set numbers, no GitHub API needed

# ---- palette (matches banner) ----
BG1, BG2 = "#141321", "#1b1033"
PURPLE, CYAN, PINK, YELLOW, GREEN = "#a78bfa", "#A9FEF7", "#FE428E", "#F8D847", "#05FFA1"
LEVELS = ["#1c1a30", "#0d4b3b", "#0a8a5f", "#05d484", GREEN]

QUERY = """
query($login:String!,$from:DateTime!,$to:DateTime!){
  user(login:$login){
    createdAt
    contributionsCollection(from:$from,to:$to){
      totalCommitContributions totalIssueContributions
      totalPullRequestContributions totalPullRequestReviewContributions
      contributionCalendar{weeks{contributionDays{date contributionCount}}}
    }
  }
}"""


LANG_QUERY = """
query($login:String!){
  user(login:$login){
    repositories(first:100, ownerAffiliations:OWNER, isFork:false, orderBy:{field:PUSHED_AT,direction:DESC}){
      nodes{ languages(first:8, orderBy:{field:SIZE,direction:DESC}){ edges{ size node{ name color } } } }
    }
  }
}"""


def gql(variables, query=QUERY):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        raise SystemExit(f"GitHub API error: {data['errors']}")
    return data["data"]["user"]


def fetch_live():
    if not TOKEN:
        raise SystemExit("Set GH_TOKEN (or GITHUB_TOKEN) or use --demo")
    now = datetime.now(timezone.utc)
    days, totals = {}, dict(commits=0, issues=0, prs=0, reviews=0)
    y, created_year = now.year, None
    while True:
        frm = f"{y}-01-01T00:00:00Z"
        to = now.strftime("%Y-%m-%dT%H:%M:%SZ") if y == now.year else f"{y}-12-31T23:59:59Z"
        u = gql({"login": LOGIN, "from": frm, "to": to})
        if created_year is None:
            created_year = int(u["createdAt"][:4])
        cc = u["contributionsCollection"]
        totals["commits"] += cc["totalCommitContributions"]
        totals["issues"] += cc["totalIssueContributions"]
        totals["prs"] += cc["totalPullRequestContributions"]
        totals["reviews"] += cc["totalPullRequestReviewContributions"]
        for w in cc["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]
        if y <= created_year:
            break
        y -= 1
    return days, totals


def fetch_languages(top=6):
    """Returns [(name, color, percent)] for the top languages across your own repos."""
    try:
        u = gql({"login": LOGIN}, LANG_QUERY)
        sizes, colors = {}, {}
        for repo in u["repositories"]["nodes"]:
            for e in repo["languages"]["edges"]:
                n = e["node"]["name"]
                sizes[n] = sizes.get(n, 0) + e["size"]
                colors[n] = e["node"]["color"] or "#8b8b8b"
        total = sum(sizes.values()) or 1
        ranked = sorted(sizes.items(), key=lambda kv: -kv[1])[:top]
        return [(n, colors[n], v * 100 / total) for n, v in ranked]
    except Exception as ex:  # never break the whole panel over languages
        print("language fetch failed:", ex)
        return []


def demo_languages():
    return [("TypeScript", "#3178c6", 62.54), ("HTML", "#e34c26", 15.73), ("Python", "#3572A5", 8.19),
            ("Java", "#b07219", 6.62), ("JavaScript", "#f1e05a", 6.04), ("C++", "#f34b7d", 0.88)]


def fetch_demo():
    random.seed(7)
    today = date.today()
    days = {}
    for i in range(365 * 3):
        d = today - timedelta(days=i)
        r = random.random()
        days[d.isoformat()] = 0 if r < 0.35 else int(random.expovariate(1 / 6)) + 1
    return days, dict(commits=32500, issues=7, prs=18, reviews=3)


def streaks(days):
    items = sorted(days.items())
    longest = cur = 0
    l_start = l_end = c_start = None
    best_start = best_end = None
    for d, c in items:
        if c > 0:
            if cur == 0:
                c_start = d
            cur += 1
            if cur > longest:
                longest, best_start, best_end = cur, c_start, d
        else:
            cur = 0
    # current streak: walk back from today (today may still be 0)
    cs, cur_len, cur_start = 0, 0, None
    seq = items[::-1]
    if seq and seq[0][1] == 0:
        seq = seq[1:]
    for d, c in seq:
        if c == 0:
            break
        cur_len += 1
        cur_start = d
    return cur_len, cur_start, longest, best_start, best_end


def fmt(n):
    return f"{n:,}"


def short(n):
    return f"{n/1000:.1f}k" if n >= 10000 else fmt(n)


def nice(d):
    if not d:
        return "-"
    x = datetime.fromisoformat(d)
    return f"{x.strftime('%b')} {x.day}, {x.year}"


def level_fn(vals):
    nz = sorted(v for v in vals if v > 0)
    if not nz:
        return lambda c: 0
    t1, t2, t3 = nz[len(nz) // 4], nz[len(nz) // 2], nz[(len(nz) * 3) // 4]
    def f(c):
        if c == 0: return 0
        if c <= t1: return 1
        if c <= t2: return 2
        if c <= t3: return 3
        return 4
    return f


def build(days, totals, langs, override=None):
    W, H = 1100, 530
    today = date.today()
    total = sum(days.values())
    cur_len, cur_start, longest, l_start, l_end = streaks(days)
    ov = override or {}
    total = ov.get("total", total)
    cur_len = ov.get("cur", cur_len)
    longest = ov.get("longest", longest)
    l_start = ov.get("l_start", l_start)
    l_end = ov.get("l_end", l_end)

    # heatmap window: last 53 weeks starting on a Sunday
    start = today - timedelta(days=(today.weekday() + 1) % 7 + 52 * 7)
    window = {}
    d = start
    while d <= today:
        window[d] = days.get(d.isoformat(), 0)
        d += timedelta(days=1)
    year_total = sum(window.values())
    lvl = level_fn(window.values())
    peak = max(window.values()) if window else 0

    o = []
    a = o.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="GitHub contribution status for {LOGIN}">')
    a("<style>"
      "text{font-family:'Segoe UI',Arial,sans-serif;paint-order:stroke;stroke:#141321;stroke-width:3px;stroke-linejoin:round}"
      ".m{font-family:'Courier New',monospace}.mrain text{stroke:none}"
      "@keyframes cin{from{opacity:0}to{opacity:1}}"
      "@keyframes rise{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}"
      "@keyframes slide{from{opacity:0;transform:translateX(-30px)}to{opacity:1;transform:translateX(0)}}"
      "@keyframes scan{from{transform:translateY(-10px)}to{transform:translateY(540px)}}"
      "@keyframes pulse{0%,100%{opacity:.55}50%{opacity:1}}"
      "@keyframes draw{from{stroke-dashoffset:var(--l)}to{stroke-dashoffset:0}}"
      "@keyframes flow{to{stroke-dashoffset:-3200}}"
      "@keyframes flick{0%,92%,100%{opacity:1}93%{opacity:.35}95%{opacity:1}97%{opacity:.5}}"
      "@keyframes tw{0%,100%{opacity:1}50%{opacity:.55}}"
      "@keyframes ping{0%{transform:scale(1);opacity:.95}100%{transform:scale(2.6);opacity:0}}"
      "@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
      "@keyframes sweep{0%{transform:translateX(0)}55%,100%{transform:translateX(1500px)}}"
      "@keyframes rain{0%{transform:translateY(-24px);opacity:0}25%{opacity:.16}100%{transform:translateY(70px);opacity:0}}"
      "@keyframes mfall{from{transform:translateY(-240px)}to{transform:translateY(570px)}}"
      "@keyframes blink{0%,100%{opacity:1}50%{opacity:.15}}"
      "@keyframes glowpulse{0%,100%{opacity:.35}50%{opacity:.9}}"
      ".c{animation:cin .6s ease-out backwards}"
      ".t{animation:cin .6s ease-out backwards,tw 3s ease-in-out infinite}"
      ".rise{animation:rise .8s cubic-bezier(.2,.8,.2,1) backwards}"
      ".slide{animation:slide .7s cubic-bezier(.2,.8,.2,1) backwards}"
      ".scan{animation:scan 6s linear infinite}"
      ".ring{animation:draw 1.6s ease-out .5s backwards,pulse 2.4s ease-in-out 2.1s infinite}"
      ".flow{animation:flow 9s linear infinite}"
      ".flick{animation:flick 6s infinite}"
      ".ping{transform-box:fill-box;transform-origin:center;animation:ping 2.2s ease-out infinite}"
      ".grow{transform-box:fill-box;transform-origin:left center;animation:grow 1.1s cubic-bezier(.2,.8,.2,1) backwards}"
      ".sweep{animation:sweep 7s ease-in-out infinite}"
      ".sweep2{animation:sweep 5s ease-in-out 1.5s infinite}"
      ".mrain{animation:mfall 8s linear infinite}"
      ".live{animation:blink 1.4s ease-in-out infinite}"
      ".gp{animation:glowpulse 3s ease-in-out infinite}"
      "@media (prefers-reduced-motion:reduce){*{animation:none!important}.mrain{display:none}}"
      "</style>")
    a(f"""<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BG1}"/><stop offset="1" stop-color="{BG2}"/></linearGradient>
<linearGradient id="edge" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{PURPLE}"/><stop offset=".5" stop-color="{CYAN}"/><stop offset="1" stop-color="{PINK}"/></linearGradient>
<linearGradient id="ringg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{PINK}"/><stop offset="1" stop-color="{YELLOW}"/></linearGradient>
<linearGradient id="line" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{GREEN}" stop-opacity="0"/><stop offset=".15" stop-color="{PURPLE}"/><stop offset=".5" stop-color="{CYAN}"/><stop offset=".85" stop-color="{PURPLE}"/><stop offset="1" stop-color="{GREEN}" stop-opacity="0"/></linearGradient>
<linearGradient id="shine" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".13"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<filter id="tglow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<clipPath id="clip"><rect x="1" y="1" width="{W-2}" height="{H-2}" rx="18"/></clipPath>
<clipPath id="cardsclip"><rect x="40" y="76" width="1020" height="110" rx="10"/></clipPath>
<clipPath id="barclip"><rect x="40" y="0" width="1020" height="12" rx="6"/></clipPath>
</defs>""")
    a(f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="18" fill="url(#bg)"/>')

    # matrix digital rain: dense katakana/binary columns with a bright head
    random.seed(3)
    GLYPHS = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789"
    a('<g clip-path="url(#clip)" class="m" font-size="12" text-anchor="middle">')
    for i in range(46):
        x = 22 + i * 23.5
        n = random.randint(7, 16)
        dur, delay = random.uniform(4.5, 11), -random.uniform(0, 11)
        tint = random.choice([GREEN, GREEN, GREEN, CYAN, PURPLE])
        a(f'<g class="mrain" style="animation-duration:{dur:.1f}s;animation-delay:{delay:.1f}s">')
        for k in range(n):
            y = k * 14
            if k == n - 1:
                a(f'<text x="{x:.1f}" y="{y}" fill="#d8fff1" opacity=".55">{random.choice(GLYPHS)}</text>')
            else:
                op = 0.06 + 0.30 * (k / n) ** 1.6
                a(f'<text x="{x:.1f}" y="{y}" fill="{tint}" opacity="{op:.2f}">{random.choice(GLYPHS)}</text>')
        a("</g>")
    a("</g>")
    a(f'<rect x="30" y="244" width="{W-60}" height="184" rx="10" fill="{BG1}" fill-opacity=".80"/>')
    a(f'<rect x="30" y="438" width="{W-60}" height="84" rx="10" fill="{BG1}" fill-opacity=".80"/>')
    a(f'<g clip-path="url(#clip)"><rect class="scan" x="0" y="0" width="{W}" height="2" fill="{CYAN}" opacity=".10"/></g>')
    a(f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="18" fill="none" stroke="url(#edge)" stroke-width="1.5"/>')
    # neon runner racing around the border
    a(f'<rect class="flow" x="1" y="1" width="{W-2}" height="{H-2}" rx="18" fill="none" stroke="{CYAN}" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="110 3090" filter="url(#glow)"/>')

    # corner brackets (breathing)
    a('<g class="gp">')
    for (x, y, sx, sy) in [(14, 14, 1, 1), (W-14, 14, -1, 1), (14, H-14, 1, -1), (W-14, H-14, -1, -1)]:
        a(f'<path d="M{x} {y+18*sy} V{y} H{x+18*sx}" fill="none" stroke="{CYAN}" stroke-width="2"/>')
    a("</g>")

    # header
    a(f'<g class="flick" fill="{PINK}" filter="url(#tglow)"><path d="M40 33 L50 39 L40 45 Z"/><path d="M52 33 L62 39 L52 45 Z" fill="{CYAN}"/></g>')
    a(f'<text class="flick" x="74" y="44" font-size="17" font-weight="700" letter-spacing="6" fill="#c4b5fd" filter="url(#tglow)">CONTRIBUTION STATUS</text>')
    a(f'<circle class="live" cx="{W-366}" cy="40" r="4" fill="{GREEN}" filter="url(#glow)"/>')
    a(f'<text class="m" x="{W-40}" y="44" text-anchor="end" font-size="12" letter-spacing="2" fill="{CYAN}" opacity=".8">@{LOGIN} // SYNC {today.isoformat()}</text>')
    a(f'<rect x="40" y="56" width="{W-80}" height="2" fill="url(#line)"/>')

    # stat cards
    def card(x, w=320, y=76, h=110):
        a(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#17142a" fill-opacity=".82" stroke="#3a2f6b" stroke-width="1.2"/>')

    def big(x, num, label, sub, color, delay):
        a(f'<g class="rise" style="animation-delay:{delay}s">')
        card(x)
        a(f'<text x="{x+160}" y="{76+54}" text-anchor="middle" font-size="36" font-weight="800" fill="{color}" filter="url(#tglow)">{num}</text>')
        a(f'<text class="m" x="{x+160}" y="{76+80}" text-anchor="middle" font-size="12" letter-spacing="2" fill="#b9b4d6">{label}</text>')
        a(f'<text class="m" x="{x+160}" y="{76+98}" text-anchor="middle" font-size="10" fill="#7d77a8">{sub}</text>')
        a("</g>")

    first = ov.get("first") or (min(days) if days else today.isoformat())
    big(40, fmt(total), "TOTAL CONTRIBUTIONS", f"{nice(first)} - Present", PINK, 0.1)

    cx = 40 + 350 + 160
    a('<g class="rise" style="animation-delay:.3s">')
    card(390)
    prog = min(1.0, cur_len / longest) if longest else 0
    r = 36
    circ = 2 * 3.14159265 * r
    arc = circ * prog
    a(f'<circle cx="{cx}" cy="{76+52}" r="{r}" fill="none" stroke="#2a2548" stroke-width="5"/>')
    if arc > 0:
      a(f'<circle class="ring" style="--l:{arc:.1f}" cx="{cx}" cy="{76+52}" r="{r}" fill="none" stroke="url(#ringg)" stroke-width="5" stroke-linecap="round" '
        f'stroke-dasharray="{arc:.1f} {circ:.1f}" transform="rotate(-90 {cx} {76+52})" filter="url(#glow)"/>')
    a(f'<text x="{cx}" y="{76+60}" text-anchor="middle" font-size="{24 if len(fmt(cur_len)) <= 3 else 19}" font-weight="800" fill="{YELLOW}">{fmt(cur_len)}</text>')
    a(f'<text class="m" x="{cx}" y="{76+104}" text-anchor="middle" font-size="11" letter-spacing="2" fill="{YELLOW}">CURRENT STREAK</text>')
    a("</g>")

    big(740, fmt(longest), "LONGEST STREAK", f"{nice(l_start)} - {nice(l_end)}", PINK, 0.5)

    # light sweep across the cards
    a('<g clip-path="url(#cardsclip)"><path class="sweep" d="M-220 76 H-150 L-190 186 H-260 Z" fill="url(#shine)"/></g>')

    # mini chips
    chips = [("COMMITS", short(totals["commits"]), GREEN), ("PULL REQUESTS", fmt(totals["prs"]), CYAN),
             ("ISSUES", fmt(totals["issues"]), YELLOW), ("REVIEWS", fmt(totals["reviews"]), PURPLE)]
    for i, (lab, val, col) in enumerate(chips):
        x = 40 + i * 260
        a(f'<g class="slide" style="animation-delay:{0.7 + i*0.12:.2f}s">')
        a(f'<rect x="{x}" y="202" width="240" height="32" rx="8" fill="#17142a" stroke="{col}" stroke-opacity=".45"/>')
        a(f'<rect x="{x}" y="202" width="4" height="32" rx="2" fill="{col}"/>')
        a(f'<text class="m" x="{x+18}" y="223" font-size="11" letter-spacing="2" fill="#b9b4d6">{lab}</text>')
        a(f'<text x="{x+224}" y="224" text-anchor="end" font-size="16" font-weight="800" fill="{col}">{val}</text>')
        a("</g>")

    # heatmap
    x0, y0, pitch, size = 74, 278, 17, 14
    a(f'<text class="m" x="40" y="258" font-size="11" letter-spacing="2" fill="{CYAN}">LAST 12 MONTHS &#183; {fmt(year_total)} CONTRIBUTIONS</text>')
    for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        a(f'<text class="m" x="40" y="{y0 + row*pitch + 11}" font-size="9" fill="#7d77a8">{name}</text>')
    last_m = None
    for col in range(53):
        dd = start + timedelta(days=col * 7)
        if dd > today:
            break
        if dd.month != last_m and (col == 0 or dd.day <= 7) and not (col == 0 and (start + timedelta(days=21)).month != dd.month and (start + timedelta(days=14)).month != dd.month):
            a(f'<text class="m" x="{x0 + col*pitch}" y="{y0-6}" font-size="9" fill="#7d77a8">{dd.strftime("%b").upper()}</text>')
            last_m = dd.month
    peak_done = False
    for dd, c in window.items():
        idx = (dd - start).days
        col, row = idx // 7, (dd.weekday() + 1) % 7
        L = lvl(c)
        x, y = x0 + col * pitch, y0 + row * pitch
        fill, extra, cls = LEVELS[L], "", "c"
        delay = f"{col*0.02:.2f}s"
        if c == peak and peak > 0 and not peak_done:
            fill, extra, peak_done = PINK, f' stroke="{PINK}" stroke-opacity=".45" stroke-width="2"', True
            a(f'<rect class="ping" x="{x}" y="{y}" width="{size}" height="{size}" rx="3" fill="none" stroke="{PINK}" stroke-width="1.5"/>')
        elif L == 4:
            extra, cls = f' stroke="{GREEN}" stroke-opacity=".35" stroke-width="2"', "t"
            delay = f"{col*0.02:.2f}s,{random.uniform(0, 3):.2f}s"
        a(f'<rect class="{cls}" style="animation-delay:{delay}" x="{x}" y="{y}" width="{size}" height="{size}" rx="3" fill="{fill}"{extra}><title>{dd.isoformat()}: {c}</title></rect>')

    # heatmap legend
    lx = W - 40 - (5 * 17 + 90)
    a(f'<rect x="40" y="403" width="10" height="10" rx="2" fill="{PINK}"/>')
    a(f'<text class="m" x="56" y="412" font-size="10" fill="#7d77a8">BEST DAY: {peak}</text>')
    a(f'<text class="m" x="{lx}" y="412" font-size="10" fill="#7d77a8">LESS</text>')
    for i, colr in enumerate(LEVELS):
        a(f'<rect x="{lx+36+i*17}" y="402" width="{size}" height="{size}" rx="3" fill="{colr}"/>')
    a(f'<text class="m" x="{lx+36+5*17+4}" y="412" font-size="10" fill="#7d77a8">MORE</text>')

    # languages bar
    a(f'<rect x="40" y="428" width="{W-80}" height="2" fill="url(#line)"/>')
    a(f'<text class="m" x="40" y="454" font-size="11" letter-spacing="2" fill="{CYAN}">MOST USED LANGUAGES</text>')
    if langs:
        tot = sum(p for _, _, p in langs) or 1
        bx, bw, by = 40, W - 80, 464
        a(f'<rect x="{bx}" y="{by}" width="{bw}" height="12" rx="6" fill="#2a2548"/>')
        a(f'<g transform="translate(0 {by})"><g clip-path="url(#barclip)">')
        cx_ = bx
        for i, (n, col, p) in enumerate(langs):
            w = bw * p / tot
            a(f'<rect class="grow" style="animation-delay:{0.9 + i*0.15:.2f}s" x="{cx_:.1f}" y="0" width="{max(w-2, 2):.1f}" height="12" fill="{col}"/>')
            cx_ += w
        a('<path class="sweep2" d="M-220 0 H-150 L-170 12 H-240 Z" fill="url(#shine)"/>')
        a("</g></g>")
        cw = bw / len(langs)
        for i, (n, col, p) in enumerate(langs):
            x = bx + i * cw
            a(f'<g class="slide" style="animation-delay:{1.4 + i*0.1:.2f}s">')
            a(f'<circle cx="{x+6:.1f}" cy="500" r="5" fill="{col}" filter="url(#glow)"/>')
            a(f'<text x="{x+18:.1f}" y="504" font-size="12" font-weight="600" fill="#e6e3ff">{escape(n)}</text>')
            a(f'<text class="m" x="{x+18:.1f}" y="518" font-size="10" fill="#7d77a8">{p*100/tot:.2f}%</text>')
            a("</g>")
    else:
        a('<text class="m" x="40" y="490" font-size="11" fill="#7d77a8">no language data yet</text>')

    a("</svg>")
    return "\n".join(o)


if __name__ == "__main__":
    override = None
    if STATIC:
        # EDIT THESE NUMBERS to your own, then run: python generate_contributions.py --static
        days, totals = fetch_demo()
        langs = demo_languages()
        today_ = date.today().isoformat()
        override = dict(total=33977, cur=2524, longest=2524, first="2020-01-01",
                        l_start="2020-01-01", l_end=today_)
        totals = dict(commits=32500, issues=7, prs=18, reviews=0)
    elif DEMO:
        days, totals = fetch_demo()
        langs = demo_languages()
    else:
        days, totals = fetch_live()
        langs = fetch_languages()
    svg = build(days, totals, langs, override)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {OUT} ({len(svg)} bytes)")
