"""Render borderless GitHub profile statistics from validated public data."""

from datetime import date, timedelta
from html import escape
import json
import math


def text(x, y, value, color, size=14, weight=400, extra=""):
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" {extra}>{escape(str(value))}</text>'


def colors(config, dark):
    return {"ink":"#dce4f2" if dark else "#26354a", "muted":"#8b9bb4" if dark else "#65758d", "line":"#263449" if dark else "#e4eaf3", "accent":config["accent"] if dark else config["lightAccent"], "second":config["secondary"]}


def document(w, h, title, body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="title"><title id="title">{escape(title)}</title><style>text{{font-family:"Segoe UI",Arial,sans-serif}}</style>{body}</svg>\n'


def overview(data, config, dark):
    c=colors(config,dark)
    body=text(24,31,data["username"]+"'s GitHub Stats",c["accent"],20,650)
    metrics=[("Stars earned",data["stars"],"star"),("Contributions (365 days)",data["contributions"],"code"),("Public repositories",data["public_repos"],"repo"),("Followers",data["followers"],"people")]
    paths={"star":'M8 1 10 6l5 .5-4 3.5 1 5-4-2.5L4 15l1-5-4-3.5L6 6Z',"code":'m5 3-4 5 4 5m6-10 4 5-4 5M9 1 7 15',"repo":'M2 2h11v12H2Zm0 9h11M5 2v9',"people":'M8 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM2 16v-2a6 6 0 0 1 12 0v2'}
    for i,(label,value,icon) in enumerate(metrics):
        y=74+i*33
        body+=f'<g transform="translate(25 {y-13})" fill="none" stroke="{c["accent"]}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="{paths[icon]}"/></g>'
        body+=text(55,y,label,c["ink"],14,500)
        body+=text(430,y,f'{value:,}',c["ink"],15,650,'text-anchor="end"')
    body+=text(24,218,"Public GitHub data · "+data["updated"],c["muted"],11)
    return document(470,236,data["username"]+" GitHub statistics",body)


LANGUAGE_COLORS={"C#":"#b28df5","Go":"#55cce4","TypeScript":"#5599ee","JavaScript":"#f2d366","HTML":"#f08379","CSS":"#b190f4","Python":"#5c9fe1","C++":"#e787b9","C":"#a8b2c7","Vue":"#59cfa4","Shell":"#a6d276","PowerShell":"#6995ee"}


def languages(data, config, dark):
    c=colors(config,dark)
    body=text(20,31,"Most Used Languages",c["accent"],20,650)
    entries=[dict(entry) for entry in data["languages"][:5]]
    if len(data["languages"])>5:
        entries.append({"name":"Other","bytes":sum(x["bytes"] for x in data["languages"][5:])})
    total=sum(x["bytes"] for x in entries)
    if not total:
        body+=text(20,110,"No public language data yet",c["muted"],15)
    else:
        circumference=2*math.pi*53
        offset=0
        for index,entry in enumerate(entries):
            fraction=entry["bytes"]/total
            color=LANGUAGE_COLORS.get(entry["name"],config["secondary"])
            body+=f'<circle cx="78" cy="124" r="53" fill="none" stroke="{color}" stroke-width="15" stroke-dasharray="{fraction*circumference:.3f} {circumference:.3f}" stroke-dashoffset="{-offset:.3f}" transform="rotate(-90 78 124)"/>'
            offset+=fraction*circumference
            y=78+index*23
            body+=f'<circle cx="161" cy="{y-5}" r="4" fill="{color}"/>'
            body+=text(173,y,entry["name"],c["ink"],12,500)
            body+=text(342,y,f'{fraction*100:.1f}%',c["muted"],12,extra='text-anchor="end"')
        body+=text(78,127,"CODE",c["muted"],12,600,'text-anchor="middle" letter-spacing="1"')
    body+=text(20,218,"Original public repositories only",c["muted"],11)
    return document(360,236,data["username"]+" public code languages",body)


def streak_values(data):
    today=date.fromisoformat(data["updated"])
    counts=data["calendar"]
    current_day=today if counts[today.isoformat()] else today-timedelta(days=1)
    current=0
    while counts.get(current_day.isoformat(),0):
        current+=1
        current_day-=timedelta(days=1)
    longest=running=0
    for count in counts.values():
        running=running+1 if count else 0
        longest=max(longest,running)
    return current,longest


def streak(data, config, dark, mobile=False):
    c=colors(config,dark)
    current,longest=streak_values(data)
    values=[(data["contributions"],"Contributions / 365 days"),(current,"Current streak / days"),(longest,"Longest streak / 365 days")]
    body=''
    if mobile:
        labels=['Contributions','Current streak','Longest streak']
        for i,(value,_) in enumerate(values):
            x=70+140*i
            body+=text(x,64,value,c['accent'] if i==1 else c['ink'],34,650,'text-anchor="middle"')
            body+=text(x,96,labels[i],c['muted'],12,extra='text-anchor="middle"')
            body+=text(x,117,'365 days' if i==0 else 'days',c['muted'],10,extra='text-anchor="middle"')
        return document(420,142,data['username']+' contribution streaks',body)
    for i,(value,label) in enumerate(values):
        x=145+305*i
        if i:
            body+=f'<line x1="{x-153}" y1="40" x2="{x-153}" y2="136" stroke="{c["line"]}"/>'
        if i==1:
            body+=f'<circle cx="{x}" cy="78" r="49" fill="none" stroke="{c["accent"]}" stroke-width="2"/>'
        body+=text(x,92,value,c["accent"] if i==1 else c["ink"],40,650,'text-anchor="middle"')
        body+=text(x,153,label,c["muted"],14,extra='text-anchor="middle"')
    return document(900,178,f'{data["username"]}: {current} current streak, {longest} longest streak in the last 365 days',body)


def activity(data, config, dark):
    c=colors(config,dark)
    today=date.fromisoformat(data["updated"])
    first=today-timedelta(days=29)
    values=[data["calendar"][(first+timedelta(days=i)).isoformat()] for i in range(30)]
    maximum=max(1,max(values))
    ceiling=maximum if maximum<=5 else math.ceil(maximum/5)*5
    left,right,top,bottom=45,866,63,203
    points=[(left+i*(right-left)/29,bottom-value*(bottom-top)/ceiling) for i,value in enumerate(values)]
    body=text(28,30,"Contribution activity · Last 30 days",c["accent"],20,650)
    for ratio in [0,.5,1]:
        y=bottom-(bottom-top)*ratio
        body+=f'<line x1="{left}" y1="{y}" x2="{right}" y2="{y}" stroke="{c["line"]}" stroke-dasharray="3 5"/>'
        body+=text(32,y+4,f'{ceiling*ratio:g}',c["muted"],11,extra='text-anchor="end"')
    line=' '.join(('M' if i==0 else 'L')+f'{x:.2f},{y:.2f}' for i,(x,y) in enumerate(points))
    body+=f'<defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop stop-color="{c["accent"]}" stop-opacity=".25"/><stop offset="1" stop-color="{c["accent"]}" stop-opacity="0"/></linearGradient></defs><path d="{line} L{right},{bottom} L{left},{bottom} Z" fill="url(#area)"/><path d="{line}" fill="none" stroke="{c["accent"]}" stroke-width="2.5" stroke-linejoin="round"/>'
    for i,(x,y) in enumerate(points):
        if values[i]:
            body+=f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.5" fill="{c["second"]}"><title>{first+timedelta(days=i)}: {values[i]} contributions</title></circle>'
    for index in [0,7,14,21,29]:
        body+=text(points[index][0],225,(first+timedelta(days=index)).strftime('%b %d'),c["muted"],11,extra='text-anchor="middle"')
    return document(900,245,data["username"]+" 30-day public contribution activity",body)


def badges(data, config, dark):
    c=colors(config,dark)
    labels=[("GitHub",data["username"],"#242a35"),("Stars",str(data["stars"]),"#b77822"),("Followers",str(data["followers"]),"#4a83cd")]
    body=''
    x=0
    for label,value,color in labels:
        a=len(label)*6.5+18
        b=len(value)*6.5+18
        body+=f'<rect x="{x}" y="0" width="{a+b}" height="26" rx="4" fill="{color}"/><rect x="{x}" y="0" width="{a}" height="26" rx="4" fill="#343c4c"/>'
        body+=text(x+a/2,17,label,"#fff",11,500,'text-anchor="middle"')
        body+=text(x+a+b/2,17,value,"#fff",11,500,'text-anchor="middle"')
        x+=a+b+9
    return document(x-9,26,data["username"]+" social badges",body)


def render(root, config, data):
    output=root/"assets"
    output.mkdir(parents=True,exist_ok=True)
    files={}
    for dark in [False,True]:
        suffix=("-dark" if dark else "")+".svg"
        for name,renderer in [("stats",overview),("languages",languages),("streak",streak),("activity",activity),("social",badges)]:
            files[name+suffix]=renderer(data,config,dark)
        files['streak-mobile'+suffix]=streak(data,config,dark,mobile=True)
    files["public-stats.json"]=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    for name,content in files.items():
        temporary=output/(name+'.tmp')
        temporary.write_text(content,encoding='utf-8',newline='\n')
        temporary.replace(output/name)
