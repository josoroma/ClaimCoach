import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve,dirname} from 'node:path';
const directory=dirname(fileURLToPath(import.meta.url));
const mode=process.argv[2]||'render';
if(!['render','check','preview','snapshot'].includes(mode))throw new Error('Use render, check, preview, or snapshot.');
const args=['--yes','--package','hyperframes@0.8.171','--','hyperframes',mode];
if(mode==='render')args.push('--fps','30','--quality','looks','--workers','2','--output',resolve(directory,'claimcoach-walkthrough.en.mp4'));
if(mode==='snapshot'){
  const film=JSON.parse(readFileSync(resolve(directory,'composition/data.json'),'utf8'));
  args.push('--at',film.scenes.map(s=>(s.start+Math.min(4,s.duration/2)).toFixed(3)).join(','));
}
args.push(...process.argv.slice(3));
const result=spawnSync('npx',args,{cwd:resolve(directory,'composition'),stdio:'inherit',env:{...process.env,DO_NOT_TRACK:'1'}});
if(result.error)throw result.error;
process.exit(result.status??1);
