import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {dirname,resolve,extname,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
const here=dirname(fileURLToPath(import.meta.url));
const puppeteer=(await import(process.env.PUPPETEER_MODULE||'puppeteer')).default;
const types={'.html':'text/html','.mjs':'application/javascript','.js':'application/javascript','.json':'application/json','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.wav':'audio/wav','.ttf':'font/ttf'};
const server=createServer(async(req,res)=>{try{let path=decodeURIComponent(new URL(req.url,'http://localhost').pathname);if(path.endsWith('/'))path+='index.html';const full=resolve(here,'.'+path);if(!full.startsWith(here+sep))throw Error('invalid');res.setHeader('Content-Type',types[extname(full)]||'application/octet-stream');res.end(await readFile(full));}catch{res.statusCode=404;res.end('not found');}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const url=`http://127.0.0.1:${server.address().port}`;
const browser=await puppeteer.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--disable-gpu','--no-sandbox']});
const page=await browser.newPage();await page.setViewport({width:1920,height:1080,deviceScaleFactor:1});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const responses=[];page.on('response',r=>{if(r.status()>=400&&!r.url().endsWith('favicon.ico'))responses.push([r.status(),r.url()]);});
await mkdir(resolve(here,'qa'),{recursive:true});
try{
 await page.goto(`${url}/composition/`,{waitUntil:'networkidle0'});await page.waitForFunction(()=>window.tasterFilm?.ready);await page.evaluate(()=>window.tasterFilm.ready);
 const film=await page.evaluate(()=>window.tasterFilm.FILM);const shots=[];
 for(const s of film.scenes){const at=s.start+Math.min(4,s.duration/2);await page.evaluate(t=>window.tasterFilm.renderAt(t),at);const filename=`${s.id}.png`;await page.screenshot({path:resolve(here,'qa',filename)});shots.push({id:s.id,at,filename});}
 for(const s of film.scenes){for(const [label,offset] of [['end',s.duration-1],...(s.altScreenshot?[['alternate',s.altAt+.3]]:[]),...(s.fullUntil?[['diagram',s.fullUntil+.3],['pan',9]]:[])]){await page.evaluate(t=>window.tasterFilm.renderAt(t),s.start+offset);await page.screenshot({path:resolve(here,'qa',`${s.id}-${label}.png`)});}}
 const cuts=[];for(const s of film.scenes.slice(1)){for(const offset of [-1/30,1/30]){const at=s.start+offset;const state=await page.evaluate(t=>{const state=window.tasterFilm.renderAt(t);return{...state,visible:[...document.querySelectorAll('.scene')].filter(n=>getComputedStyle(n).display!=='none').length};},at);if(state.visible!==1)throw Error(`Invalid cut at ${at}`);cuts.push(state);}}
 const at=film.scenes[4].start+3;await page.evaluate(t=>window.tasterFilm.renderAt(t),at);const a=await page.screenshot();await page.evaluate(t=>window.tasterFilm.renderAt(t),film.duration-.1);await page.evaluate(t=>window.tasterFilm.renderAt(t),at);const b=await page.screenshot();if(!Buffer.from(a).equals(Buffer.from(b)))throw Error('Reverse seek is not pixel deterministic');
 await page.goto(`${url}/`,{waitUntil:'networkidle0'});await page.waitForFunction(()=>document.querySelector('#clock').textContent!=='Loading…');await page.click('#play');await new Promise(r=>setTimeout(r,600));await page.click('#play');const paused=await page.$eval('#seek',n=>Number(n.value));await new Promise(r=>setTimeout(r,300));const after=await page.$eval('#seek',n=>Number(n.value));if(after!==paused)throw Error('Pause advanced');await page.click('#restart');if(await page.$eval('#seek',n=>Number(n.value))!==0)throw Error('Restart failed');
 await page.evaluate(()=>document.activeElement.blur());await page.keyboard.press('ArrowRight');if(Math.abs(await page.$eval('#seek',n=>Number(n.value))-5)>.04)throw Error('Keyboard seek failed');
 await page.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);await page.reload({waitUntil:'networkidle0'});await page.waitForFunction(()=>document.querySelector('#clock').textContent!=='Loading…');if(await page.$eval('#seek',n=>Number(n.value))!==0)throw Error('Unsolicited playback');await page.setViewport({width:390,height:844,deviceScaleFactor:1});await page.screenshot({path:resolve(here,'qa','preview-mobile.png')});const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);if(overflow)throw Error('Narrow preview overflows');
 const report={checkedAt:new Date().toISOString(),duration:film.duration,draft:film.draft,screenshots:shots,cutStates:cuts,reverseSeekPixelIdentical:true,pause:true,restart:true,keyboardSeek:true,reducedMotionNoAutoplay:true,narrowViewportNoOverflow:true,pageErrors:errors,failedResponses:responses};await writeFile(resolve(here,'qa','verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));if(errors.length||responses.length)process.exitCode=1;
}finally{await browser.close();server.close();}
