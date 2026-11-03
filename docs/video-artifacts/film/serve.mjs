import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {dirname,resolve,extname,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=dirname(fileURLToPath(import.meta.url));
const types={'.html':'text/html','.mjs':'application/javascript','.js':'application/javascript','.json':'application/json','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.wav':'audio/wav','.mp4':'video/mp4','.ttf':'font/ttf','.srt':'text/plain'};
const port=Number(process.env.PORT||4189);
const server=createServer(async(req,res)=>{try{let path=decodeURIComponent(new URL(req.url,'http://localhost').pathname);if(path.endsWith('/'))path+='index.html';const full=resolve(root,'.'+path);if(!full.startsWith(root+sep))throw Error('Invalid path');res.setHeader('Content-Type',types[extname(full)]||'application/octet-stream');res.end(await readFile(full));}catch{res.statusCode=404;res.end('Not found');}});
server.listen(port,'127.0.0.1',()=>console.log(`ClaimCoach film preview: http://127.0.0.1:${port}`));
