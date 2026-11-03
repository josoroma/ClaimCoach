import {spawnSync} from 'node:child_process';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const here=dirname(fileURLToPath(import.meta.url)),video=resolve(here,'claimcoach-walkthrough.en.mp4');
const run=(cmd,args)=>{const r=spawnSync(cmd,args,{encoding:'utf8',maxBuffer:8*1024*1024});if(r.status!==0)throw Error(r.stderr||r.stdout);return r;};
const probe=JSON.parse(run('ffprobe',['-v','error','-show_format','-show_streams','-of','json',video]).stdout);
const data=JSON.parse(await readFile(resolve(here,'composition/data.json'),'utf8'));
const v=probe.streams.find(s=>s.codec_type==='video'),a=probe.streams.find(s=>s.codec_type==='audio');
if(!v||v.width!==1920||v.height!==1080||v.codec_name!=='h264'||v.r_frame_rate!=='30/1')throw Error('Wrong video stream');
if(!a||a.codec_name!=='aac')throw Error('Missing AAC narration');
if(Math.abs(Number(probe.format.duration)-data.duration)>.12)throw Error('Unexpected video duration');
await mkdir(resolve(here,'qa/decoded'),{recursive:true});
const frames=[];
for(const s of data.scenes){const at=s.start+Math.min(4,s.duration/2);const file=`${s.id}.png`;run('ffmpeg',['-v','error','-y','-ss',String(at),'-i',video,'-frames:v','1',resolve(here,'qa/decoded',file)]);frames.push({at,file});}
for(const s of data.scenes){for(const [label,offset] of [['end',s.duration-1],...(s.altScreenshot?[['alternate',s.altAt+.3]]:[])]){const at=s.start+offset;const file=`${s.id}-${label}.png`;run('ffmpeg',['-v','error','-y','-ss',String(at),'-i',video,'-frames:v','1',resolve(here,'qa/decoded',file)]);frames.push({at,file});}}
for(const s of data.scenes.slice(1)){for(const delta of [-1/30,1/30]){const at=s.start+delta;const file=`cut-${s.id}-${delta<0?'before':'after'}.png`;run('ffmpeg',['-v','error','-y','-ss',String(at),'-i',video,'-frames:v','1',resolve(here,'qa/decoded',file)]);frames.push({at,file});}}
run('ffmpeg',['-v','error','-y','-ss','4','-i',video,'-frames:v','1',resolve(here,'poster.png')]);
const volume=run('ffmpeg',['-hide_banner','-i',video,'-vn','-af','volumedetect','-f','null','-']).stderr.split('\n').filter(s=>/mean_volume|max_volume|n_samples/.test(s));
if(!volume.some(s=>/n_samples: [1-9]/.test(s)))throw Error('Empty narration stream');
const report={video,expectedDuration:data.duration,format:probe.format,videoStream:v,audioStream:a,volume,decodedFrames:frames};
await writeFile(resolve(here,'qa/video-verification.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({file:video,duration:probe.format.duration,resolution:[v.width,v.height],fps:v.r_frame_rate,videoCodec:v.codec_name,audioCodec:a.codec_name,volume,decodedFrames:frames.length},null,2));
