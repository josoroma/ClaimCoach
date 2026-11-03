const data=await fetch('./data.json').then(r=>r.json());
const clamp=x=>Math.max(0,Math.min(1,x));
const ease=x=>{x=clamp(x);return x*x*(3-2*x);};
const esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const header=s=>`<div class="header"><div class="brand"><img src="assets/logo.svg" alt="ClaimCoach">ClaimCoach</div><div class="eyebrow">${esc(s.kicker)}<span class="chapter">${String(data.scenes.indexOf(s)+1).padStart(2,'0')} / ${String(data.scenes.length).padStart(2,'0')}</span></div></div>`;
const flow=(labels)=>`<div class="flow">${labels.map(([label,detail],i)=>`${i?'<div class="arrow">→</div>':''}<div class="node"><small>${detail}</small><strong>${label}</strong></div>`).join('')}</div>`;
const graphic=`<div class="hero-graphic"><div class="doc"></div><div class="stamp"><img src="assets/logo.svg" alt=""></div></div>`;
const capture=s=>`<div class="capture" data-layout-allow-overflow>${s.hasScreen?`<img src="assets/screenshots/${s.screenshot}" alt="Actual Hermes Desktop capture: ${esc(s.title)}">${s.altScreenshot?`<img class="alternate" src="assets/screenshots/${s.altScreenshot}" alt="Additional actual desktop capture: ${esc(s.title)}">`:""}`:'<div class="draft-message">AUTHORING PREVIEW<br>Awaiting the real desktop capture</div>'}<span class="capture-meta">ACTUAL HERMES DESKTOP · GUIDED STILL</span>${s.note?`<span class="evidence-note">${esc(s.note)}</span>`:""}${s.highlight?'<div class="highlight"></div>':''}</div>`;
const local=`<aside class="local-diagram"><h2>On this Mac</h2><p>Local server endpoints.<br>Weights read from <strong>~/Models</strong>.</p><div class="local-box"><strong>Hermes Desktop</strong><small>Chat → local language model</small></div><div class="local-arrow">↓</div><div class="local-box"><strong>ClaimCoach worker</strong><small>127.0.0.1:18200</small></div><div class="local-arrow">↓</div><div class="local-box"><strong>Task models</strong><small>Read · explain · draft</small></div></aside>`;
const loop=`<div class="loop-canvas"><div class="loop-top">REQUEST → TOOL → EVIDENCE → NEXT STEP</div><div class="loop-grid">${[['Read your request','Use the skill’s playbook.'],['Choose a tool','Retrieve codes, rules or a case summary.'],['Inspect the result','Ground the next step in returned evidence.'],['Continue or answer','A person reviews the proposed result.']].map(([title,sub],i)=>`<div class="loop-node"><div class="number">${i+1}</div><h2>${title}</h2><p>${sub}</p></div>`).join('')}</div><div class="loop-return"><span>Repeat when more evidence is needed</span></div><div class="loop-support"><div><strong>Command</strong>/denial &lt;case ID&gt;</div><div><strong>Skill</strong>denial-triage</div><div><strong>Tools</strong>codes · rules · summary</div></div></div>`;
document.querySelector('#stage').innerHTML=data.scenes.map(s=>`<section class="scene clip ${s.type === 'capture' ? 'capture-scene' : s.type}" id="${s.id}" data-start="${s.start}" data-duration="${s.duration}" data-track-index="1">${header(s)}${s.type==='intro'?`<div class="hero"><h1>A denial specialist<br><span>on your laptop.</span></h1><p class="lede">Practical guidance for the next claim.<br>Private evidence. A person in control.</p><div class="pill">A plugin for Hermes Desktop</div>${graphic}</div>${flow([['Add evidence','01 / INTAKE'],['Understand','02 / DIAGNOSE'],['Review a draft','03 / ACT'],['Record outcome','04 / LEARN']])}<div class="hero-note">PRODUCT WALKTHROUGH · FICTIONAL CASE DATA</div>`:s.type==='close'?`<div class="hero"><h1>Give every biller<br><span>a clearer next step.</span></h1><p class="lede">Specialist workflow on a consumer laptop.<br>Private, local inference. Reviewable work.</p>${graphic}</div>${flow([['Open ClaimCoach','CONNECT'],['Bring the evidence','UNDERSTAND'],['Review the result','DECIDE']])}<div class="credits">Independent Hermes plugin · Taster film · Synthetic English voice: Chatterbox Multilingual V3</div>`:`<div class="titlebar"><h1>${esc(s.title)}</h1><span class="tag">${esc(s.tag)}</span></div>${s.type==='loop'?loop:capture(s)}${s.type==='local'?local:''}<div class="instruction">${esc(s.instruction||'Your request → the Hermes agent → plugin tools → a reviewable answer')}</div>`}</section>`).join('');
function renderAt(t){
 t=Math.max(0,Math.min(data.duration,Number.isFinite(t)?t:0));
 const selected=data.scenes.find(s=>t>=s.start&&t<s.start+s.duration)||data.scenes.at(-1);
 for(const s of data.scenes){
  const node=document.getElementById(s.id),localTime=t-s.start,active=s===selected;
  node.style.display=active?'block':'none';if(!active)continue;
  const enter=ease(localTime/.55);
  const title=node.querySelector('.hero,.titlebar');title.style.opacity=.4+.6*enter;title.style.transform=`translateY(${(1-enter)*20}px)`;
  const alternate=!!s.altScreenshot&&localTime>=s.altAt;node.querySelectorAll('.capture img').forEach(i=>i.style.visibility=(i.classList.contains('alternate')===alternate)?'visible':'hidden');const image=node.querySelector(alternate?'.capture img.alternate':'.capture img:not(.alternate)');
  if(image){
   const box=image.parentElement,cw=box.clientWidth,ch=box.clientHeight,iw=image.naturalWidth||1920,ih=image.naturalHeight||1080;
   const fit=Math.min(cw/iw,ch/ih),initial=[(cw-iw*fit)/2,(ch-ih*fit)/2,fit];let target=initial;
   if(s.focus){let focus=alternate?s.altFocus:s.focus;if(s.panFocus){const pan=ease((localTime-s.panAt)/1.5);focus=focus.map((v,i)=>v+(s.panFocus[i]-v)*pan);}const [x,y,w,h]=focus,scale=Math.min(cw/w,ch/h);target=[(cw-w*scale)/2-x*scale,(ch-h*scale)/2-y*scale,scale];}
   const p=alternate?1:ease((localTime-1.1)/1.8),mix=(a,b)=>a+(b-a)*p,scale=mix(initial[2],target[2]);
   Object.assign(image.style,{width:`${iw*scale}px`,height:`${ih*scale}px`,left:`${mix(initial[0],target[0])}px`,top:`${mix(initial[1],target[1])}px`});
  }
  node.querySelectorAll('.flow .node').forEach((n,i)=>{const reveal=ease((localTime-.8-i*.7)/.8);n.style.opacity=.3+.7*reveal;n.style.transform=`translateY(${(1-reveal)*18}px)`;});
  const doc=node.querySelector('.doc');if(doc)doc.style.transform=`translateY(${(1-ease((localTime-.4)/1.2))*25}px) rotate(${-7+ease((localTime-.5)/2)*2}deg)`;
  const stamp=node.querySelector('.stamp');if(stamp){const p=ease((localTime-1.2)/1);stamp.style.opacity=p;stamp.style.transform=`scale(${.8+.2*p}) rotate(${(1-p)*8}deg)`;}
  node.querySelectorAll('.local-box').forEach((n,i)=>{const p=ease((localTime-1.2-i*2.1)/.8);n.style.borderColor=p>.5?'#0f5e59':'#a9c9bd';n.style.opacity=.45+.55*p;});
  const current=Math.floor(Math.max(0,localTime-1)/3.1)%4;
  node.querySelectorAll('.loop-node').forEach((n,i)=>{n.style.borderColor=i===current?'#0f5e59':'#b4cfc2';n.style.background=i===current?'#d4e9dc':'#f6f5ef';n.style.transform=`translateY(${i===current?-6:0}px)`;});
  const high=node.querySelector('.highlight');if(high){const [x,y,w,h]=s.highlight;Object.assign(high.style,{left:`${x}%`,top:`${y}%`,width:`${w}%`,height:`${h}%`,opacity:ease((localTime-2)/.6)});}
 }
 const cap=data.captions.find(c=>t>=c.start&&t<c.end);const subtitles=document.querySelector('#subtitles');subtitles.textContent=cap?.text||'';subtitles.style.visibility=cap?'visible':'hidden';
 document.querySelector('#progress').style.transform=`scaleX(${t/data.duration})`;
 document.documentElement.dataset.frame=String(Math.floor(t*data.fps));
 return{time:t,scene:selected.id};
}
window.addEventListener('hf-seek',e=>renderAt(e.detail.time));
window.tasterFilm={renderAt,FILM:data};
window.tasterFilm.ready=Promise.all([document.fonts.ready,...Array.from(document.images,i=>i.decode())]).then(()=>renderAt(0));
renderAt(0);
