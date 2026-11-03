import {readFile,writeFile,mkdir,copyFile,access} from 'node:fs/promises';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
const here=dirname(fileURLToPath(import.meta.url));
const source=JSON.parse(await readFile(resolve(here,'script.en.json'),'utf8'));
const draft=process.argv.includes('--draft');
let audio={scenes:{}};
try{audio=JSON.parse(await readFile(resolve(here,'../audio/en/manifest.json'),'utf8'));}catch(e){if(!draft)throw new Error('Final English narration manifest is required. Use --draft only for authoring.');}
const exists=async p=>{try{await access(p);return true;}catch{return false;}};
const scenes=[];let start=0;
await mkdir(resolve(here,'composition/assets/audio'),{recursive:true});
await mkdir(resolve(here,'composition/assets/screenshots'),{recursive:true});
const captions=[];
for(const scene of source.scenes){
  const a=audio.scenes[scene.id];
  if(!a&&!draft)throw new Error(`Missing narration: ${scene.id}`);
  if(a&&a.text!==scene.narration&&!draft)throw new Error(`Narration text mismatch: ${scene.id}`);
  const audioDuration=a?.duration??scene.narration.split(/\s+/).length/2.6;
  const duration=Math.ceil((audioDuration+1.2)*30)/30;
  const screenFile=scene.screenshot&&resolve(here,'../screenshots',scene.screenshot);
  const hasScreen=screenFile?await exists(screenFile):false;
  if(scene.screenshot&&!hasScreen&&!draft)throw new Error(`Missing real capture: ${screenFile}`);
  if(hasScreen)await copyFile(screenFile,resolve(here,'composition/assets/screenshots',scene.screenshot));
  if(scene.altScreenshot)await copyFile(resolve(here,'../screenshots',scene.altScreenshot),resolve(here,'composition/assets/screenshots',scene.altScreenshot));
  if(a)await copyFile(resolve(here,'../audio/en',a.file),resolve(here,'composition/assets/audio',`${scene.id}.wav`));
  let captionTime=start+.5;
  const spokenSegments=a?.segments||[{text:scene.narration,duration:audioDuration}];
  for(const spoken of spokenSegments){
    const words=spoken.text.split(/\s+/),chunks=[];
    for(let i=0;i<words.length;i+=12)chunks.push(words.slice(i,i+12).join(' '));
    for(const text of chunks){const dt=spoken.duration*text.split(/\s+/).length/words.length;captions.push({start:captionTime,end:captionTime+dt,text});captionTime+=dt;}
    captionTime+=.12;
  }
  scenes.push({...scene,start,duration,audioDuration,audio:!!a,hasScreen});
  start+=duration;
}
const film={...source,duration:start,draft,scenes,captions};
await writeFile(resolve(here,'composition/data.json'),JSON.stringify(film,null,2)+'\n');
const html=`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ClaimCoach — Product walkthrough</title><link rel="stylesheet" href="film.css"></head><body><main id="film" data-composition-id="claimcoach-film" data-no-timeline data-width="1920" data-height="1080" data-duration="${start}" data-fps="30"><div id="stage"></div><div id="subtitles" aria-live="off"></div><div id="progress"></div>${scenes.filter(s=>s.audio).map(s=>`<audio id="voice-${s.id}" class="clip" src="assets/audio/${s.id}.wav" data-start="${s.start+.5}" data-duration="${s.audioDuration}" data-track-index="20" preload="auto"></audio>`).join('')}</main><script type="module" src="film.mjs"></script></body></html>`;
await writeFile(resolve(here,'composition/index.html'),html);
const timestamp=seconds=>{const ms=Math.round(seconds*1000);return`${String(Math.floor(ms/3600000)).padStart(2,'0')}:${String(Math.floor(ms/60000)%60).padStart(2,'0')}:${String(Math.floor(ms/1000)%60).padStart(2,'0')},${String(ms%1000).padStart(3,'0')}`;};
await writeFile(resolve(here,'claimcoach.en.srt'),captions.map((c,i)=>`${i+1}\n${timestamp(c.start)} --> ${timestamp(c.end)}\n${c.text}\n`).join('\n'));
console.log(JSON.stringify({draft,duration:start,scenes:scenes.map(({id,start,duration,audio,hasScreen})=>({id,start,duration,audio,hasScreen}))},null,2));
