const iframe=document.querySelector('iframe'),view=document.querySelector('.viewport'),seek=document.querySelector('#seek'),play=document.querySelector('#play');
let t=0,playing=false,last=0,film,audios=[];
new ResizeObserver(()=>iframe.style.transform=`scale(${view.clientWidth/1920})`).observe(view);
const format=x=>`${Math.floor(x/60)}:${String(Math.floor(x%60)).padStart(2,'0')}`;
function syncAudio(){for(const {audio,start,end} of audios){if(playing&&t>=start&&t<end){const local=t-start;if(Math.abs(audio.currentTime-local)>.3)audio.currentTime=local;audio.play().catch(()=>{});}else{audio.pause();if(t<start)audio.currentTime=0;}}}
function draw(){film.renderAt(t);seek.value=t;document.querySelector('#clock').textContent=`${format(t)} / ${format(film.FILM.duration)}`;syncAudio();}
function pause(){playing=false;play.textContent='Play';syncAudio();}
function toggle(){playing=!playing;if(t>=film.FILM.duration)t=0;play.textContent=playing?'Pause':'Play';last=performance.now();draw();}
iframe.addEventListener('load',async()=>{while(!iframe.contentWindow.tasterFilm)await new Promise(r=>setTimeout(r,30));film=iframe.contentWindow.tasterFilm;await film.ready;seek.max=film.FILM.duration;audios=film.FILM.scenes.filter(s=>s.audio).map(s=>({audio:new Audio(`composition/assets/audio/${s.id}.wav`),start:s.start+.5,end:s.start+.5+s.audioDuration}));document.querySelector('.chapters').innerHTML=film.FILM.scenes.map(s=>`<button data-at="${s.start}">${s.kicker.replace(/^\d+ \/ /,'')}</button>`).join('');document.querySelectorAll('[data-at]').forEach(b=>b.addEventListener('click',()=>{t=Number(b.dataset.at);draw();}));draw();});
play.addEventListener('click',()=>film&&toggle());document.querySelector('#restart').addEventListener('click',()=>{t=0;pause();draw();});seek.addEventListener('input',()=>{t=Number(seek.value);draw();});
document.addEventListener('keydown',e=>{if(!film||e.target.matches('input,button,a'))return;if(e.code==='Space'){e.preventDefault();toggle();}if(e.code==='ArrowRight'||e.code==='ArrowLeft'){e.preventDefault();t=Math.min(film.FILM.duration,Math.max(0,t+(e.code==='ArrowRight'?5:-5)));draw();}if(e.code==='Home'){e.preventDefault();t=0;draw();}});
document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});
function tick(now){if(film&&playing){t=Math.min(film.FILM.duration,t+Math.min((now-last)/1000,.1));if(t>=film.FILM.duration)pause();draw();}last=now;requestAnimationFrame(tick);}requestAnimationFrame(tick);
